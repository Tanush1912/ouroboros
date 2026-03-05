"""Browser automation tools using Playwright.

Requires the sandbox Docker stack to be running (worktree_up.sh).
All tools return structured Pydantic models.
"""

import base64
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_ai import tool


class ScreenshotResult(BaseModel):
    url: str
    image_base64: str = Field(description="Base64-encoded PNG screenshot")
    width: int
    height: int


class DOMNode(BaseModel):
    role: str
    name: str | None = None
    children: list["DOMNode"] = Field(default_factory=list)


DOMNode.model_rebuild()


class DOMSnapshot(BaseModel):
    url: str
    title: str
    tree: DOMNode = Field(description="Accessibility tree root node")


class UIAction(BaseModel):
    action: Literal["click", "fill", "navigate", "press", "wait"] = Field(description="Action type")
    selector: str | None = Field(default=None, description="CSS selector for the target element")
    value: str | None = Field(default=None, description="Value for fill/press actions")
    url: str | None = Field(default=None, description="URL for navigate actions")


class UIFlowResult(BaseModel):
    success: bool
    steps_completed: int
    steps_total: int
    screenshots: list[str] = Field(description="Base64 screenshots after each step")
    error: str | None = None
    final_url: str = Field(default="")


async def _get_page() -> Any:
    """Get a Playwright page instance."""
    from playwright.async_api import async_playwright

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch()
    context = await browser.new_context()
    page = await context.new_page()
    return page, browser, playwright


@tool
async def take_screenshot(url: str) -> ScreenshotResult:
    """Navigate to URL and capture screenshot. Returns base64-encoded PNG."""
    page, browser, pw = await _get_page()
    try:
        await page.goto(url, wait_until="networkidle")
        screenshot_bytes = await page.screenshot(full_page=True)
        viewport = page.viewport_size or {"width": 1280, "height": 720}
        return ScreenshotResult(
            url=url,
            image_base64=base64.b64encode(screenshot_bytes).decode(),
            width=viewport["width"],
            height=viewport["height"],
        )
    finally:
        await browser.close()
        await pw.stop()


@tool
async def snapshot_dom(url: str) -> DOMSnapshot:
    """Capture DOM accessibility tree. Returns structured DOM for analysis."""
    page, browser, pw = await _get_page()
    try:
        await page.goto(url, wait_until="networkidle")
        title = await page.title()
        snapshot = await page.accessibility.snapshot()

        def _parse(node: dict | None) -> DOMNode:
            if not node:
                return DOMNode(role="none")
            return DOMNode(
                role=node.get("role", "unknown"),
                name=node.get("name"),
                children=[_parse(c) for c in node.get("children", [])],
            )

        return DOMSnapshot(url=url, title=title, tree=_parse(snapshot))
    finally:
        await browser.close()
        await pw.stop()


@tool
async def drive_ui_flow(url: str, steps: list[UIAction]) -> UIFlowResult:
    """Execute a sequence of UI actions. Returns pass/fail + screenshots."""
    page, browser, pw = await _get_page()
    screenshots = []
    steps_completed = 0

    try:
        await page.goto(url, wait_until="networkidle")
        for step in steps:
            if step.action == "navigate" and step.url:
                await page.goto(step.url, wait_until="networkidle")
            elif step.action == "click" and step.selector:
                await page.click(step.selector)
            elif step.action == "fill" and step.selector and step.value:
                await page.fill(step.selector, step.value)
            elif step.action == "press" and step.value:
                target = step.selector or "body"
                await page.press(target, step.value)
            elif step.action == "wait":
                await page.wait_for_timeout(1000)

            screenshot_bytes = await page.screenshot()
            screenshots.append(base64.b64encode(screenshot_bytes).decode())
            steps_completed += 1

        return UIFlowResult(
            success=True,
            steps_completed=steps_completed,
            steps_total=len(steps),
            screenshots=screenshots,
            final_url=page.url,
        )
    except Exception as e:
        return UIFlowResult(
            success=False,
            steps_completed=steps_completed,
            steps_total=len(steps),
            screenshots=screenshots,
            error=str(e),
            final_url=page.url if page else "",
        )
    finally:
        await browser.close()
        await pw.stop()
