"""URL prefix handling shared by the application and dashboard."""

def apply_prefix(html: str, root_path: str) -> str:
    """Prefix app-internal nav links with the sub-path so they resolve behind a
    reverse proxy. Root-absolute URLs are used (not a <base> tag) so same-page
    fragment links keep working. A no-op at a root deployment."""
    if not root_path:
        return html
    return (
        html.replace('href="./"', f'href="{root_path}/"')
        .replace('href="guide"', f'href="{root_path}/guide"')
        .replace('href="guide#', f'href="{root_path}/guide#')
        .replace('href="docs"', f'href="{root_path}/docs"')
        .replace('action="validate"', f'action="{root_path}/validate"')
        .replace('="static/', f'="{root_path}/static/')
        .replace('data-progress-url="validate/progress"', f'data-progress-url="{root_path}/validate/progress"')
    )

