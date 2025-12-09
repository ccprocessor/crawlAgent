import os
import logging
from typing import List, Dict, Optional
from pathlib import Path
from lxml import etree
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class HTMLParser:
    """
    HTML parsing utilities
    """
    
    @staticmethod
    def parse_file(file_path: str) -> Optional[etree._Element]:
        """
        Parse HTML file using lxml
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return HTMLParser.parse_string(content)
        except Exception as e:
            logger.error(f"Error parsing file {file_path}: {e}")
            return None
    
    @staticmethod
    def parse_string(html_content: str) -> Optional[etree._Element]:
        """
        Parse HTML string using lxml
        """
        try:
            parser = etree.HTMLParser(remove_blank_text=True)
            return etree.fromstring(html_content.encode('utf-8'), parser)
        except Exception as e:
            logger.error(f"Error parsing HTML string: {e}")
            return None
    
    @staticmethod
    def get_text_content(html_content: str) -> str:
        """
        Extract text content from HTML using BeautifulSoup
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            return soup.get_text(separator=' ', strip=True)
        except Exception as e:
            logger.error(f"Error extracting text: {e}")
            return ""
    
    @staticmethod
    def load_html_files(directory: str) -> List[Dict[str, str]]:
        """
        Load all HTML files from a directory
        """
        html_files = []
        dir_path = Path(directory)
        
        if not dir_path.exists():
            logger.error(f"Directory does not exist: {directory}")
            return html_files
        
        for html_file in dir_path.glob('*.html'):
            try:
                with open(html_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                html_files.append({
                    'path': str(html_file),
                    'name': html_file.name,
                    'content': content
                })
            except Exception as e:
                logger.error(f"Error loading {html_file}: {e}")
        
        logger.info(f"Loaded {len(html_files)} HTML files from {directory}")
        return html_files
    
    @staticmethod
    def get_body_content(html_content: str) -> str:
        """
        Extract body content from HTML
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            body = soup.find('body')
            if body:
                return str(body)
            return html_content
        except Exception as e:
            logger.error(f"Error extracting body: {e}")
            return html_content

