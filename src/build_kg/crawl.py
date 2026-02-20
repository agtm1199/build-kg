#!/usr/bin/env python3
"""
Simple Crawl4AI script for crawling webpages with configurable parameters.
"""

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import List, Set
from urllib.parse import urlparse

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig


class WebCrawler:
    def __init__(
        self,
        start_url: str,
        delay_ms: int = 1000,
        output_format: str = "markdown",
        max_pages: int = 10,
        max_depth: int = 2,
        output_dir: str = "./output"
    ):
        """
        Initialize the web crawler.

        Args:
            start_url: Starting URL to crawl
            delay_ms: Delay between page visits in milliseconds
            output_format: Output format (markdown, html, json)
            max_pages: Maximum number of pages to visit
            max_depth: Maximum depth for recursive crawling
            output_dir: Directory to store output files
        """
        self.start_url = start_url
        self.delay_ms = delay_ms
        self.output_format = output_format.lower()
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.output_dir = Path(output_dir)

        self.visited_urls: Set[str] = set()
        self.pages_crawled = 0

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Domain restriction (only crawl same domain)
        self.base_domain = urlparse(start_url).netloc

    def is_same_domain(self, url: str) -> bool:
        """Check if URL is from the same domain as start URL."""
        return urlparse(url).netloc == self.base_domain

    def get_output_filename(self, url: str, depth: int) -> str:
        """Generate a safe filename from URL."""
        parsed = urlparse(url)
        # Create filename from path
        path = parsed.path.strip('/').replace('/', '_')
        if not path:
            path = 'index'

        # Add timestamp and depth
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        ext = self.output_format if self.output_format != 'markdown' else 'md'

        return f"{path}_depth{depth}_{timestamp}.{ext}"

    def save_content(self, url: str, result, depth: int):
        """Save crawled content to file."""
        filename = self.get_output_filename(url, depth)
        filepath = self.output_dir / filename

        try:
            if self.output_format == "markdown":
                content = result.markdown.raw_markdown
                filepath.write_text(content, encoding='utf-8')
            elif self.output_format == "html":
                content = result.cleaned_html
                filepath.write_text(content, encoding='utf-8')
            elif self.output_format == "json":
                data = {
                    "url": result.url,
                    "title": result.url,
                    "depth": depth,
                    "status_code": result.status_code,
                    "success": result.success,
                    "markdown": result.markdown.raw_markdown,
                    "html": result.cleaned_html,
                    "links": {
                        "internal": [link['href'] for link in result.links.get('internal', [])],
                        "external": [link['href'] for link in result.links.get('external', [])]
                    },
                    "crawled_at": datetime.now().isoformat()
                }
                filepath.write_text(json.dumps(data, indent=2), encoding='utf-8')

            print(f"✓ Saved: {filename}")
        except Exception as e:
            print(f"✗ Error saving {url}: {e}")

    def extract_links(self, result) -> List[str]:
        """Extract internal links from crawl result."""
        links = []
        if result.links and 'internal' in result.links:
            for link in result.links['internal']:
                href = link.get('href', '')
                if href and self.is_same_domain(href):
                    links.append(href)
        return links

    async def crawl_page(self, crawler: AsyncWebCrawler, url: str, depth: int):
        """Crawl a single page."""
        if url in self.visited_urls:
            return []

        if self.pages_crawled >= self.max_pages:
            return []

        if depth > self.max_depth:
            return []

        self.visited_urls.add(url)
        self.pages_crawled += 1

        print(f"\n[{self.pages_crawled}/{self.max_pages}] Crawling (depth {depth}): {url}")

        try:
            # Configure crawler run
            config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                page_timeout=30000,
                wait_for="css:body"  # Wait for body to load
            )

            # Crawl the page
            result = await crawler.arun(url=url, config=config)

            if result.success:
                print(f"  Status: {result.status_code}")

                # Save content
                self.save_content(url, result, depth)

                # Add delay before next request
                if self.delay_ms > 0:
                    await asyncio.sleep(self.delay_ms / 1000.0)

                # Extract links for further crawling
                links = self.extract_links(result)
                return links
            else:
                print(f"  ✗ Failed: {result.error_message}")
                return []

        except Exception as e:
            print(f"  ✗ Error: {e}")
            return []

    async def crawl(self):
        """Main crawling function with depth-first search."""
        print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    Web Crawler Started                        ║
╚══════════════════════════════════════════════════════════════╝

Configuration:
  Start URL:      {self.start_url}
  Delay:          {self.delay_ms}ms
  Output Format:  {self.output_format}
  Max Pages:      {self.max_pages}
  Max Depth:      {self.max_depth}
  Output Dir:     {self.output_dir.absolute()}

Starting crawl...
""")

        # Configure browser
        browser_config = BrowserConfig(
            headless=True,
            enable_stealth=True
        )

        # Start crawler
        async with AsyncWebCrawler(config=browser_config) as crawler:
            # Queue of (url, depth) tuples
            queue = [(self.start_url, 0)]

            while queue and self.pages_crawled < self.max_pages:
                url, depth = queue.pop(0)

                # Crawl page and get new links
                new_links = await self.crawl_page(crawler, url, depth)

                # Add new links to queue if within depth limit
                if depth < self.max_depth:
                    for link in new_links:
                        if link not in self.visited_urls:
                            queue.append((link, depth + 1))

        print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    Crawling Complete!                         ║
╚══════════════════════════════════════════════════════════════╝

Summary:
  Pages Crawled:  {self.pages_crawled}
  Output Files:   {len(list(self.output_dir.glob('*')))}
  Output Dir:     {self.output_dir.absolute()}
""")


def main():
    """Main entry point with configuration."""

    parser = argparse.ArgumentParser(
        description="Web crawler using Crawl4AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic crawl with default settings
  python crawl_script.py --url https://example.com

  # Crawl with custom parameters
  python crawl_script.py --url https://docs.example.com --delay 2000 --format json --pages 50 --depth 3

  # Save to custom directory
  python crawl_script.py --url https://example.com --output /path/to/output
        """
    )

    parser.add_argument(
        "-u", "--url",
        dest="start_url",
        required=True,
        help="Starting URL to crawl (required)"
    )

    parser.add_argument(
        "-d", "--delay",
        dest="delay_ms",
        type=int,
        default=1000,
        help="Delay between page visits in milliseconds (default: 1000)"
    )

    parser.add_argument(
        "-f", "--format",
        dest="output_format",
        choices=["markdown", "html", "json"],
        default="markdown",
        help="Output file format (default: markdown)"
    )

    parser.add_argument(
        "-p", "--pages",
        dest="max_pages",
        type=int,
        default=10,
        help="Maximum number of pages to visit (default: 10)"
    )

    parser.add_argument(
        "--depth",
        dest="max_depth",
        type=int,
        default=2,
        help="Maximum crawl depth (default: 2)"
    )

    parser.add_argument(
        "-o", "--output",
        dest="output_dir",
        default="./output",
        help="Output directory for saved files (default: ./output)"
    )

    args = parser.parse_args()

    # Convert args to config dictionary
    config = {
        "start_url": args.start_url,
        "delay_ms": args.delay_ms,
        "output_format": args.output_format,
        "max_pages": args.max_pages,
        "max_depth": args.max_depth,
        "output_dir": args.output_dir
    }

    # Create and run crawler
    crawler = WebCrawler(**config)
    asyncio.run(crawler.crawl())


if __name__ == "__main__":
    main()
