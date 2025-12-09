import logging
from typing import List, Optional, Dict, Any
from lxml import etree
from lxml.etree import _Element

logger = logging.getLogger(__name__)


class XPathExtractor:
    """
    XPath extraction utilities
    """
    
    @staticmethod
    def get_xpath(element: _Element) -> str:
        """
        Generate XPath for an element
        """
        if element is None:
            return ""
        
        parts = []
        while element is not None and element.tag is not None:
            index = 0
            parent = element.getparent()
            
            if parent is not None:
                siblings = [s for s in parent if s.tag == element.tag]
                if len(siblings) > 1:
                    index = siblings.index(element) + 1
                    parts.append(f"{element.tag}[{index}]")
                else:
                    parts.append(element.tag)
            else:
                parts.append(element.tag)
            
            element = parent
        
        return '/' + '/'.join(reversed(parts))
    
    @staticmethod
    def find_by_xpath(tree: _Element, xpath: str) -> List[_Element]:
        """
        Find elements by XPath
        """
        try:
            return tree.xpath(xpath)
        except Exception as e:
            logger.error(f"Error executing XPath {xpath}: {e}")
            return []
    
    @staticmethod
    def find_common_xpath(elements: List[_Element]) -> Optional[str]:
        """
        Find common XPath pattern for a list of elements
        """
        if not elements:
            return None
        
        xpaths = [XPathExtractor.get_xpath(elem) for elem in elements]
        
        # Find common prefix
        common_parts = []
        min_parts = min(len(xp.split('/')) for xp in xpaths)
        
        for i in range(min_parts):
            parts = [xp.split('/')[i] for xp in xpaths]
            if len(set(parts)) == 1:
                common_parts.append(parts[0])
            else:
                break
        
        if common_parts:
            return '/'.join(common_parts)
        
        return xpaths[0] if xpaths else None
    
    @staticmethod
    def extract_text_by_xpath(tree: _Element, xpath: str) -> List[str]:
        """
        Extract text content using XPath
        """
        elements = XPathExtractor.find_by_xpath(tree, xpath)
        return [elem.text_content().strip() if elem.text_content() else "" 
                for elem in elements]
    
    @staticmethod
    def suggest_xpath_patterns(tree: _Element, sample_text: str) -> List[str]:
        """
        Suggest XPath patterns that might match given text
        """
        suggestions = []
        
        # Try to find element containing the text
        all_elements = tree.xpath('//*')
        for elem in all_elements:
            text = elem.text_content().strip()
            if sample_text.lower() in text.lower()[:100]:  # Check first 100 chars
                xpath = XPathExtractor.get_xpath(elem)
                suggestions.append(xpath)
                if len(suggestions) >= 5:
                    break
        
        return suggestions

