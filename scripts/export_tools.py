"""Bundle the tool workbench as one downloadable HTML file; stdlib only."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def main():
    root = Path(__file__).resolve().parents[1]
    frontend = root / "src" / "frontend"
    html = (frontend / "tools.html").read_text()
    html = html.replace("<head>",
                        '<head>\n  <meta name="travel-tools-transport" content="browser">')
    css = (frontend / "static" / "tools.css").read_text()
    javascript = (frontend / "static" / "tools.js").read_text()
    html = html.replace('<link rel="stylesheet" href="/static/tools.css">',
                        f"<style>\n{css}\n</style>")
    html = html.replace('<script defer src="/static/tools.js"></script>', "")
    html = html.replace('</body>', f'<script>\n{javascript}\n</script>\n</body>')
    html = html.replace('href="/"', 'href="https://github.com/Forevermyhero/cs222-project"')
    output = root / "docs" / "travel-tools.html"
    output.write_text(html)
    entry = ZipInfo("travel-tools.html", date_time=(1980, 1, 1, 0, 0, 0))
    entry.compress_type = ZIP_DEFLATED
    entry.external_attr = 0o100644 << 16
    with ZipFile(output.with_suffix(".zip"), "w") as archive:
        archive.writestr(entry, html.encode())
    print(output)


if __name__ == "__main__":
    main()
