import json
import logging
from typing import List, Dict, Any, Optional
from openai import OpenAI
from config import Settings

logger = logging.getLogger(__name__)


class AnalyzerAgent:
    """
    Analysis agent that uses AI to analyze HTML structure
    and identify content patterns
    """
    
    def __init__(self):
        # Use OpenAI client for custom endpoints (OpenAI-compatible API)
        # If using official Anthropic API, can switch to Anthropic client
        self.client = OpenAI(
            api_key=Settings.ANTHROPIC_API_KEY,
            base_url=Settings.ANTHROPIC_BASE_URL
        )
        self.model = Settings.ANTHROPIC_MODEL
    
    def analyze_html_structure(self, html_content: str, file_path: str) -> Dict[str, Any]:
        """
        Analyze HTML structure and identify content sections
        """
        prompt = self._build_analysis_prompt(html_content, file_path)
        
        try:
            # Use OpenAI-compatible API format
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )
            
            # Handle response - should be a ChatCompletion object
            if hasattr(response, 'choices') and len(response.choices) > 0:
                result_text = response.choices[0].message.content
            else:
                logger.error(f"Unexpected response format: {type(response)}")
                return {"error": f"Unexpected response format: {type(response)}"}
            
            # Try to extract JSON from the response
            try:
                return json.loads(result_text)
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code blocks
                import re
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', result_text, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(1))
                
                # Return structured result
                return {
                    "file": file_path,
                    "analysis": result_text,
                    "raw_response": True
                }
        except Exception as e:
            logger.error(f"Error analyzing {file_path}: {e}")
            return {
                "file": file_path,
                "error": str(e)
            }
    
    def analyze_multiple_files(self, html_contents: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        Analyze multiple HTML files and return combined results
        """
        results = []
        for item in html_contents:
            result = self.analyze_html_structure(item['content'], item['path'])
            results.append(result)
        return results
    
    def _build_analysis_prompt(self, html_content: str, file_path: str) -> str:
        # Truncate HTML if too long
        max_length = 500000
        if len(html_content) > max_length:
            html_content = html_content[:max_length] + "\n... [truncated]"
        
        return f"""Analyze the following HTML file structure and identify key content sections.

File: {file_path}

HTML Content:
{html_content}

Please analyze this HTML and identify:
1. Main content sections (title, body, comments, metadata, etc.)
2. XPath expressions to locate each section
3. Patterns that identify similar elements (e.g., all comment items)
4. Structural characteristics of each section

For each section, provide:
- Section name/type (e.g., "article_title", "article_body", "comments_list", "comment_item")
- XPath expression to locate it
- Description of what it contains
- Whether it's a list/collection of items
- Any distinguishing attributes or patterns

Return your analysis as JSON in this format:
{{
    "file": "{file_path}",
    "sections": [
        {{
            "name": "section_name",
            "type": "title|body|comment|metadata|other",
            "xpath": "xpath_expression",
            "description": "What this section represents",
            "is_list": false,
            "list_xpath": "xpath_for_list_items (if applicable)",
            "attributes": {{"class": "...", "id": "..."}},
            "content_sample": "sample text from this section"
        }}
    ],
    "patterns": {{
        "common_classes": [...],
        "common_ids": [...],
        "structural_patterns": [...]
    }},
    "notes": "Any additional observations"
}}"""

