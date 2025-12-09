import os
import logging
import re
from typing import List, Dict, Optional
from pathlib import Path
import requests
from urllib.parse import urlparse
import time

logger = logging.getLogger(__name__)


class URLDownloader:
    """
    Download HTML content from URLs
    """
    
    @staticmethod
    def load_urls_from_file(file_path: str) -> List[str]:
        """
        Load URLs from a text file
        Supports comments (lines starting with #)
        """
        urls = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if line and not line.startswith('#'):
                        # Validate URL format
                        if URLDownloader._is_valid_url(line):
                            urls.append(line)
                        else:
                            logger.warning(f"Invalid URL format, skipping: {line}")
            logger.info(f"Loaded {len(urls)} URLs from {file_path}")
            return urls
        except Exception as e:
            logger.error(f"Error loading URLs from {file_path}: {e}")
            return []
    
    @staticmethod
    def _is_valid_url(url: str) -> bool:
        """Check if string is a valid URL"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False
    
    @staticmethod
    def download_html(url: str, timeout: int = 30, retries: int = 3) -> Optional[str]:
        """
        Download HTML content from a URL
        """
        # Parse URL to get domain for Referer
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'Referer': base_url,  # Add Referer header
            'Origin': base_url  # Add Origin header for same-origin requests
        }
        
        # Use Session to maintain cookies and connection pooling
        session = requests.Session()
        session.headers.update(headers)
        
        for attempt in range(retries):
            try:
                # Add random delay between retries to avoid rate limiting
                if attempt > 0:
                    delay = 2 ** attempt + (attempt * 0.5)  # Exponential backoff with jitter
                    time.sleep(delay)
                
                response = session.get(url, timeout=timeout, allow_redirects=True)
                response.raise_for_status()
                
                # Try to detect encoding
                if response.encoding:
                    content = response.text
                else:
                    # Fallback to UTF-8
                    content = response.content.decode('utf-8', errors='ignore')
                
                logger.info(f"Successfully downloaded: {url} ({len(content)} chars)")
                session.close()
                return content
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"Attempt {attempt + 1}/{retries} failed for {url}: {e}")
                if attempt < retries - 1:
                    # Exponential backoff with jitter
                    delay = 2 ** attempt + (attempt * 0.5)
                    time.sleep(delay)
                else:
                    logger.error(f"Failed to download {url} after {retries} attempts")
                    session.close()
                    return None
    
    @staticmethod
    def download_multiple_urls(urls: List[str], output_dir: Optional[str] = None) -> List[Dict[str, str]]:
        """
        Download HTML from multiple URLs
        Returns list of dicts with 'path', 'name', 'content', 'url'
        
        Args:
            urls: List of URLs to download
            output_dir: Output directory. If provided and is an existing directory (not a flow directory),
                       files will be saved directly to that directory. Otherwise, files will be saved to
                       output_dir/downloaded_html/ subdirectory.
        """
        html_files = []
        
        # Determine target directory
        if output_dir:
            output_path = Path(output_dir)
            # If output_dir is an input/html directory, save directly there
            # Otherwise, save to downloaded_html subdirectory
            if 'html' in output_path.name and output_path.parent.name in ['typcial', 'spread', 'typical']:
                # This is an input/html directory, save directly
                temp_dir = output_path
                temp_dir.mkdir(parents=True, exist_ok=True)
            else:
                # This is an output directory, save to downloaded_html subdirectory
                temp_dir = output_path / 'downloaded_html'
                temp_dir.mkdir(parents=True, exist_ok=True)
        else:
            temp_dir = None
        
        for i, url in enumerate(urls, 1):
            logger.info(f"Downloading [{i}/{len(urls)}]: {url}")
            
            # Add delay between requests to avoid rate limiting
            if i > 1:
                delay = 1.0 + (i % 3) * 0.5  # 1-2.5 seconds delay
                time.sleep(delay)
            
            content = URLDownloader.download_html(url)
            
            if content:
                # Generate unique filename from URL
                parsed = urlparse(url)
                # Get path parts
                path_parts = [p for p in parsed.path.split('/') if p]
                
                if path_parts:
                    # Use last 2-3 parts of path to create meaningful filename
                    # e.g., /2025/10/15/secure-coding-in-javascript/ -> secure-coding-in-javascript
                    if len(path_parts) >= 2:
                        # Use last part, or combine last 2 parts if last is too short
                        if len(path_parts[-1]) >= 5:
                            filename = path_parts[-1]
                        else:
                            filename = '_'.join(path_parts[-2:])
                    else:
                        filename = path_parts[-1]
                else:
                    # If no path, use domain name with index
                    filename = f"{parsed.netloc.replace('.', '_')}_{i:03d}"
                
                # Clean filename - remove invalid characters
                filename = re.sub(r'[^\w\-_\.]', '_', filename)
                
                # If filename is still empty or too short, use index with number
                if not filename or len(filename) < 3:
                    filename = f"page_{i:03d}"
                
                # Ensure .html extension
                if not filename.endswith('.html'):
                    filename += '.html'
                
                # Check if file already exists, add index if needed
                if temp_dir:
                    base_filename = filename
                    counter = 1
                    while (temp_dir / filename).exists():
                        name_part = base_filename.rsplit('.html', 1)[0]
                        filename = f"{name_part}_{counter}.html"
                        counter += 1
                
                # Save to temp directory if specified
                file_path = None
                if temp_dir:
                    file_path = str(temp_dir / filename)
                    try:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                    except Exception as e:
                        logger.warning(f"Failed to save {file_path}: {e}")
                
                html_files.append({
                    'path': file_path or url,
                    'name': filename,
                    'content': content,
                    'url': url
                })
            else:
                logger.error(f"Skipping {url} due to download failure")
        
        logger.info(f"Successfully downloaded {len(html_files)}/{len(urls)} URLs")
        return html_files

