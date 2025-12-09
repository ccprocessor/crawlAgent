import json
import logging
from typing import Dict, Any, Optional
from config import Settings

logger = logging.getLogger(__name__)

# Try to import Anthropic, fallback to OpenAI
try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logger.warning("Anthropic package not available, falling back to OpenAI")

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI package not available")


class CodeGeneratorAgent:
    """
    Code generator agent that creates extraction code based on JSON schema
    Supports both Anthropic and OpenAI APIs
    """
    
    def __init__(self):
        # Determine which API to use based on configuration
        # Use Anthropic if base_url is set and not the default OpenAI endpoint
        # Check if it's a custom Anthropic endpoint (like opensphereai)
        base_url_lower = (Settings.ANTHROPIC_BASE_URL or "").lower()
        use_anthropic = (
            ANTHROPIC_AVAILABLE and 
            Settings.ANTHROPIC_BASE_URL and 
            (base_url_lower != 'https://api.anthropic.com' and
             ('opensphereai' in base_url_lower or
              'anthropic' in base_url_lower or
              not base_url_lower.startswith('http://35.220.164.252')))  # Not the OpenAI endpoint
        )
        
        if use_anthropic and ANTHROPIC_AVAILABLE:
            self.client_type = 'anthropic'
            self.client = Anthropic(
                api_key=Settings.ANTHROPIC_API_KEY,
                base_url=Settings.ANTHROPIC_BASE_URL
            )
            self.model = Settings.ANTHROPIC_MODEL
            logger.info(f"Using Anthropic API for code generation: {Settings.ANTHROPIC_BASE_URL}")
        elif OPENAI_AVAILABLE:
            self.client_type = 'openai'
            self.client = OpenAI(
                api_key=Settings.OPENAI_API_KEY,
                base_url=Settings.OPENAI_BASE_URL
            )
            self.model = Settings.OPENAI_MODEL
            logger.info(f"Using OpenAI API for code generation: {Settings.OPENAI_BASE_URL}")
        else:
            raise ImportError("Neither Anthropic nor OpenAI packages are available")
    
    def generate_extraction_code(self, json_schema: Dict[str, Any], language: str = 'python') -> str:
        """
        Generate extraction code based on JSON schema
        """
        # Check schema size and optimize if needed
        schema_str = json.dumps(json_schema, indent=2, ensure_ascii=False)
        schema_size = len(schema_str)
        
        # If schema is too large, use a simplified version
        # Increased threshold to support larger schemas (100KB)
        SCHEMA_SIZE_THRESHOLD = 100000  # ~100KB
        if schema_size > SCHEMA_SIZE_THRESHOLD:
            logger.warning(f"Schema is very large ({schema_size} chars), using simplified version for prompt")
            json_schema = self._simplify_schema(json_schema)
        else:
            logger.info(f"Schema size: {schema_size} chars (within limit of {SCHEMA_SIZE_THRESHOLD})")
        
        prompt = self._build_code_generation_prompt(json_schema, language)
        prompt_size = len(prompt)
        logger.info(f"Code generation prompt size: {prompt_size} chars")
        
        # Retry logic for API calls
        max_retries = 3
        retry_delay = 2  # seconds
        
        for attempt in range(max_retries):
            try:
                # Use Anthropic API if configured, otherwise OpenAI
                if self.client_type == 'anthropic':
                    # Anthropic API with thinking support (as per user's template)
                    response = self.client.messages.create(
                        model=self.model,
                        max_tokens=16000,
                        thinking={
                            "type": "enabled",
                            "budget_tokens": 10000
                        },
                        system=self._get_system_prompt(),
                        messages=[{
                            "role": "user",
                            "content": prompt
                        }]
                    )
                    
                    # Extract text from Anthropic response
                    # Response contains blocks (thinking and text)
                    code = ""
                    for block in response.content:
                        if block.type == "thinking":
                            logger.debug(f"Thinking summary: {block.thinking}")
                        elif block.type == "text":
                            code = block.text
                    
                    if not code:
                        logger.error("No text content found in Anthropic response")
                        return f"# Error: No text content in response"
                        
                else:
                    # OpenAI API
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": self._get_system_prompt()},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.2,
                        max_tokens=16000,  # Increased limit for longer code generation
                        timeout=300  # 5 minutes timeout for large schemas
                    )
                    
                    # Handle OpenAI response
                    if hasattr(response, 'choices') and len(response.choices) > 0:
                        code = response.choices[0].message.content
                    else:
                        logger.error(f"Unexpected response format: {type(response)}")
                        return f"# Error: Unexpected response format: {type(response)}"
                
                # Extract code from markdown if present
                import re
                code_match = re.search(r'```(?:python|python3)?\s*(.*?)```', code, re.DOTALL)
                if code_match:
                    return code_match.group(1).strip()
                
                return code.strip()
                
            except Exception as e:
                error_msg = str(e)
                # Check if it's a 502 or timeout error
                if "502" in error_msg or "Bad Gateway" in error_msg:
                    logger.warning(f"502 Bad Gateway error (attempt {attempt + 1}/{max_retries}). This may be due to:")
                    logger.warning(f"  - Server overload or timeout")
                    logger.warning(f"  - Request too large (prompt size: {prompt_size} chars)")
                    logger.warning(f"  - Network issues")
                
                if attempt < max_retries - 1:
                    logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {e}. Retrying in {retry_delay} seconds...")
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error(f"Failed to generate extraction code after {max_retries} attempts: {e}")
                    logger.info("Using fallback code generator...")
                    # Return a basic template code as fallback
                    return self._generate_fallback_code(json_schema)
    
    def _get_system_prompt(self) -> str:
        return """You are an expert code generator specializing in HTML content extraction.
You MUST generate code that STRICTLY follows the required interface specification.
DO NOT create custom method names or return types - follow the specification EXACTLY.
The code must be production-ready, robust, and handle edge cases."""
    
    def _build_code_generation_prompt(self, json_schema: Dict[str, Any], language: str) -> str:
        schema_json = json.dumps(json_schema, indent=2, ensure_ascii=False)
        
        # Count sections for logging
        sections_count = len(json_schema.get('sections', []))
        
        return f"""Generate {language} code to extract content from HTML files based on the following JSON schema:

{schema_json}

CRITICAL INTERFACE REQUIREMENTS (MUST BE STRICTLY FOLLOWED):
===========================================================

1. CLASS DEFINITION (MANDATORY):
   - MUST define a class named exactly 'HTMLExtractor' (case-sensitive)
   - MUST have __init__ method with EXACT signature:
     def __init__(self, schema: Dict[str, Any], logger: Optional[logging.Logger] = None) -> None:
   - Parameter name MUST be 'schema' (not 'json_schema', not 'extraction_schema', etc.)
   - Parameter type MUST be Dict[str, Any]
   - logger parameter is optional with default None

2. EXTRACT METHOD (MANDATORY):
   - MUST have a method named exactly 'extract' (NOT extract_from_string, extract_from_file, extract_content, etc.)
   - Method signature MUST be EXACTLY:
     def extract(self, html_content: Optional[str] = None, file_path: Optional[str] = None) -> Dict[str, Any]:
   - Parameter names MUST be exactly: 'html_content' and 'file_path' (no variations like 'html_str', 'path', etc.)
   - Both parameters are Optional with default None
   - Return type annotation MUST be: -> Dict[str, Any]
   - Return value MUST be a plain Python dictionary (NOT ExtractionResult, NOT dataclass, NOT list, NOT other types)
   - Dictionary keys MUST be section names from the schema
   - Dictionary values MUST be extracted content (str, list, None, etc.)

3. IMPLEMENTATION REQUIREMENTS:
   - Use lxml (etree) for HTML parsing (preferred) or BeautifulSoup
   - Implement robust XPath-based extraction
   - Handle missing elements gracefully (return None for single values, [] for lists)
   - Include comprehensive error handling (try-except blocks)
   - Add clear comments explaining extraction logic
   - Use Python boolean values (True/False) NOT JSON boolean values (true/false)
   - Use pathlib.Path or os.path.join() for cross-platform path handling
   - When html_content is provided, use it directly
   - When file_path is provided, read the file and parse it
   - Extract all {sections_count} sections defined in the schema

4. SCHEMA CONSTANT (OPTIONAL BUT RECOMMENDED):
   - MAY define SCHEMA constant at module level: SCHEMA: Dict[str, Any] = {{...}}
   - If defined, should match the schema structure passed to __init__

5. FORBIDDEN:
   - DO NOT create methods named extract_from_string, extract_from_file, extract_content, etc.
   - DO NOT return ExtractionResult, dataclass, or any custom result type
   - DO NOT use different parameter names (html_str, path, file, etc.)
   - DO NOT create wrapper functions or alternative interfaces

EXAMPLE INTERFACE (MUST FOLLOW THIS EXACT STRUCTURE):
```python
from typing import Dict, Any, Optional
import logging
from lxml import etree, html

class HTMLExtractor:
    def __init__(self, schema: Dict[str, Any], logger: Optional[logging.Logger] = None) -> None:
        self.schema = schema
        self.sections = schema.get("sections", [])
        self.logger = logger or logging.getLogger(__name__)
    
    def extract(self, html_content: Optional[str] = None, file_path: Optional[str] = None) -> Dict[str, Any]:
        # Implementation here
        # Must return Dict[str, Any] with section names as keys
        result = {{}}
        for section in self.sections:
            section_name = section.get("name")
            # ... extract content ...
            result[section_name] = extracted_value
        return result
```

Generate the complete code following this EXACT interface specification."""
    
    def _simplify_schema(self, json_schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simplify schema to reduce prompt size while keeping essential information
        """
        simplified = {
            "schema_version": json_schema.get("schema_version", "1.0"),
            "description": json_schema.get("description", ""),
            "sections": []
        }
        
        sections = json_schema.get('sections', [])
        # Keep only essential fields for each section
        for section in sections:
            simplified_section = {
                "name": section.get("name", ""),
                "description": section.get("description", ""),
                "xpath": section.get("xpath", ""),
                "is_list": section.get("is_list", False)
            }
            # Only include xpath_list if it exists and is different from xpath
            if "xpath_list" in section and section.get("xpath") != section.get("xpath_list", [None])[0]:
                simplified_section["xpath_list"] = section["xpath_list"][:3]  # Limit to first 3
        
            simplified["sections"].append(simplified_section)
        
        logger.info(f"Simplified schema from {len(sections)} sections, keeping essential fields only")
        return simplified
    
    def _generate_fallback_code(self, json_schema: Dict[str, Any]) -> str:
        """
        Generate a basic fallback code template when API fails
        """
        # Convert JSON schema to Python-compatible format
        # Replace JSON false/true with Python False/True
        sections_json = json.dumps(json_schema.get('sections', []), indent=8, ensure_ascii=False)
        # Replace JSON boolean values with Python boolean values
        sections_json = sections_json.replace(': false', ': False').replace(': true', ': True')
        
        return f'''# HTML Content Extraction Code
# Generated from schema (API generation failed, using fallback template)

from lxml import etree
from typing import Dict, Any, List, Optional
import json
import logging

logger = logging.getLogger(__name__)

def extract_content(html_content: str) -> Dict[str, Any]:
    """
    Extract content from HTML based on schema
    
    Args:
        html_content: HTML content as string
        
    Returns:
        Dictionary with extracted content
    """
    try:
        parser = etree.HTMLParser()
        tree = etree.fromstring(html_content.encode('utf-8'), parser)
        
        result = {{}}
        
        # Extract sections from schema
        sections = {sections_json}
        
        for section in sections:
            name = section.get('name', '')
            xpath = section.get('xpath', '')
            is_list = section.get('is_list', False)
            
            if not xpath:
                continue
                
            try:
                elements = tree.xpath(xpath)
                
                if is_list:
                    result[name] = [elem.text or '' for elem in elements if elem is not None]
                else:
                    result[name] = elements[0].text if elements and elements[0] is not None else None
            except Exception as e:
                logger.warning(f"Failed to extract {{name}}: {{e}}")
                result[name] = [] if is_list else None
        
        return result
        
    except Exception as e:
        logger.error(f"Error parsing HTML: {{e}}")
        return {{}}

if __name__ == "__main__":
    # Example usage
    # Use pathlib.Path for cross-platform path handling to avoid escape sequence warnings
    from pathlib import Path
    
    # Example: process a single HTML file
    example_file = Path("example.html")
    if example_file.exists():
        with open(example_file, "r", encoding="utf-8") as f:
            html = f.read()
        
        result = extract_content(html)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("Example file not found. Please provide HTML content directly.")
        print("Usage: result = extract_content(html_string)")
'''

