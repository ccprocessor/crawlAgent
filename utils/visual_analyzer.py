import base64
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from openai import OpenAI
from config import Settings
from playwright.sync_api import sync_playwright
from PIL import Image
import io

logger = logging.getLogger(__name__)


class VisualAnalyzer:
    """
    Visual analysis agent using vision models to analyze HTML structure
    """
    
    def __init__(self):
        self.client = OpenAI(
            api_key=Settings.VISION_API_KEY,
            base_url=Settings.VISION_BASE_URL
        )
        self.model = Settings.VISION_MODEL
    
    def analyze_html_visually(self, html_content: str, file_path: str) -> Dict[str, Any]:
        """
        Analyze HTML by rendering it and using vision model
        """
        try:
            # Render HTML to image
            screenshot = self._render_html_to_image(html_content)
            if not screenshot:
                return {"error": "Failed to render HTML to image"}
            
            # Analyze with vision model
            analysis = self._analyze_image(screenshot, file_path)
            return analysis
        except Exception as e:
            logger.error(f"Error in visual analysis: {e}")
            return {"error": str(e)}
    
    def _render_html_to_image(self, html_content: str, width: int = 1920, height: int = 1080) -> Optional[bytes]:
        """
        Render HTML to image using Playwright
        """
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width': width, 'height': height})
                
                # Create a data URL
                html_data_url = f"data:text/html;charset=utf-8,{html_content}"
                page.goto(html_data_url)
                page.wait_for_load_state('networkidle', timeout=5000)
                
                screenshot = page.screenshot(full_page=True)
                browser.close()
                
                return screenshot
        except Exception as e:
            logger.error(f"Error rendering HTML: {e}")
            # Fallback: try with Selenium if Playwright fails
            return self._render_with_selenium(html_content)
    
    def _render_with_selenium(self, html_content: str) -> Optional[bytes]:
        """
        Fallback rendering method using Selenium
        """
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            
            options = Options()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1920,1080')
            
            driver = webdriver.Chrome(options=options)
            driver.get(f"data:text/html;charset=utf-8,{html_content}")
            
            screenshot = driver.get_screenshot_as_png()
            driver.quit()
            
            return screenshot
        except Exception as e:
            logger.error(f"Error with Selenium rendering: {e}")
            return None
    
    def _analyze_image(self, image_bytes: bytes, file_path: str) -> Dict[str, Any]:
        """
        Analyze rendered image using vision model
        """
        try:
            # Convert to base64
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            prompt = self._build_visual_prompt(file_path)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                temperature=0.3
            )
            
            # Handle response - should be a ChatCompletion object
            if hasattr(response, 'choices') and len(response.choices) > 0:
                result_text = response.choices[0].message.content
            else:
                logger.error(f"Unexpected response format: {type(response)}")
                return {"error": f"Unexpected response format: {type(response)}"}
            
            # Try to parse as JSON
            import json
            import re
            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(0))
                except:
                    pass
            
            return {
                "file": file_path,
                "visual_analysis": result_text,
                "raw_response": True
            }
        except Exception as e:
            logger.error(f"Error analyzing image: {e}")
            return {"error": str(e)}
    
    def _build_visual_prompt(self, file_path: str) -> str:
        return f"""Analyze this rendered HTML page and identify the visual structure and content sections.

File: {file_path}

Please identify:
1. Main content areas (header, body, sidebar, footer, comments section, etc.)
2. Visual patterns that indicate content types (e.g., comment blocks, article sections)
3. Layout structure and how content is organized
4. Any repeating patterns (like comment items, list items, etc.)

For each identified section, describe:
- What type of content it appears to be
- Its visual characteristics (position, size, styling patterns)
- How to identify similar sections in other pages

Return your analysis as JSON:
{{
    "file": "{file_path}",
    "visual_sections": [
        {{
            "name": "section_name",
            "type": "header|body|comment|sidebar|footer|other",
            "description": "Visual description",
            "position": "top|middle|bottom|left|right",
            "characteristics": ["visual", "characteristics"],
            "likely_xpath_hints": ["class patterns", "id patterns"]
        }}
    ],
    "layout_structure": "description of overall layout",
    "repeating_patterns": ["pattern1", "pattern2"],
    "notes": "Additional visual observations"
}}"""

