from browserjev.dom import parse_page


def test_parse_page_extracts_visible_text_and_same_origin_links():
    html = """
    <html><head><title>Employee Committee</title><style>.x{}</style></head>
    <body>
      <nav><a href="/benefits">Benefits</a><a href="/benefits#top">Duplicate</a></nav>
      <main><h1>Welcome employees</h1><p>Ticketing and gift cards.</p></main>
      <a href="https://external.example/ad">External</a>
      <a href="mailto:team@example.com">Email</a>
      <script>secretNoise()</script>
    </body></html>
    """
    page = parse_page("https://cse.example/", html)
    assert page.title == "Employee Committee"
    assert "Welcome employees" in page.text
    assert "secretNoise" not in page.text
    assert [(link.url, link.label) for link in page.links] == [
        ("https://cse.example/benefits", "Benefits")
    ]


def test_parse_page_limits_text_and_link_candidates():
    links = "".join(f'<a href="/p/{i}">Page {i}</a>' for i in range(20))
    page = parse_page(
        "https://example.com",
        f"<body>{'x' * 100}{links}</body>",
        max_text=40,
        max_links=3,
    )
    assert len(page.text) == 40
    assert len(page.links) == 3
