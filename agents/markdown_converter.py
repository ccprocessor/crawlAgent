import json
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
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


class MarkdownConverterAgent:
    """
    Markdown converter agent that:
    1. Analyzes JSON extraction results to identify main content fields
    2. Generates code to convert JSON to Markdown format
    3. Ensures proper Markdown syntax compliance
    """
    
    def __init__(self):
        # Determine which API to use based on configuration
        base_url_lower = (Settings.ANTHROPIC_BASE_URL or "").lower()
        use_anthropic = (
            ANTHROPIC_AVAILABLE and 
            Settings.ANTHROPIC_BASE_URL and 
            (base_url_lower != 'https://api.anthropic.com' and
             ('opensphereai' in base_url_lower or
              'anthropic' in base_url_lower or
              not base_url_lower.startswith('http://35.220.164.252')))
        )
        
        if use_anthropic:
            self.client = Anthropic(api_key=Settings.ANTHROPIC_API_KEY)
            self.model = Settings.ANTHROPIC_MODEL
            self.use_anthropic = True
        elif OPENAI_AVAILABLE:
            self.client = OpenAI(
                api_key=Settings.ANTHROPIC_API_KEY,
                base_url=Settings.ANTHROPIC_BASE_URL
            )
            self.model = Settings.ANTHROPIC_MODEL
            self.use_anthropic = False
        else:
            raise ImportError("Neither Anthropic nor OpenAI packages are available")
    
    def analyze_content_fields(self, json_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze JSON results to identify which fields contain main content
        Returns analysis of content field structure
        """
        if not json_results:
            return {"error": "No JSON results provided"}
        
        # Sample a few results to understand structure
        sample_results = json_results[:3] if len(json_results) >= 3 else json_results
        
        prompt = self._build_content_analysis_prompt(sample_results)
        
        try:
            if self.use_anthropic:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=4000,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                result = response.content[0].text
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt()},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=4000
                )
                result = response.choices[0].message.content
            
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code block
                import re
                json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', result, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(1))
                logger.warning("Failed to parse JSON, returning raw result")
                return {"raw_result": result, "error": "Failed to parse JSON response"}
        except Exception as e:
            logger.error(f"Failed to analyze content fields: {e}")
            return {"error": str(e)}
    
    def generate_markdown_converter_code(self, content_analysis: Dict[str, Any], sample_json: Dict[str, Any], retry: bool = False) -> str:
        """
        Generate Python code to convert JSON results to Markdown format
        """
        prompt = self._build_converter_generation_prompt(content_analysis, sample_json, retry=retry)
        
        try:
            if self.use_anthropic:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=8000,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                code = response.content[0].text
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt()},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=8000
                )
                code = response.choices[0].message.content
            
            # Extract code from markdown code block if present
            import re
            code_match = re.search(r'```(?:python)?\s*(.*?)\s*```', code, re.DOTALL)
            if code_match:
                return code_match.group(1).strip()
            return code.strip()
        except Exception as e:
            logger.error(f"Failed to generate markdown converter code: {e}")
            raise
    
    def _get_system_prompt(self) -> str:
        return """You are an expert in content analysis and Markdown conversion.
You analyze JSON extraction results to identify main content fields and generate
robust Python code to convert JSON to properly formatted Markdown."""
    
    def _build_content_analysis_prompt(self, sample_results: List[Dict[str, Any]]) -> str:
        sample_json = json.dumps(sample_results, indent=2, ensure_ascii=False)
        
        return f"""Analyze the following JSON extraction results and identify which fields contain the main article content (body text).

JSON Results (sample):
{sample_json}

Please identify:
1. Which fields contain the main article body/content (primary text content)
2. Which fields contain metadata (title, date, author, etc.)
3. Which fields contain structural elements (headers, navigation, etc.)
4. The hierarchy and relationships between content fields

Return your analysis as JSON with the following structure:
{{
    "main_content_fields": ["field1", "field2", ...],  // Fields that contain main article body
    "metadata_fields": ["field1", "field2", ...],     // Fields for title, date, author, etc.
    "structural_fields": ["field1", "field2", ...],   // Fields for navigation, headers, etc.
    "content_hierarchy": {{
        "primary": "field_name",                       // Primary content field
        "secondary": ["field1", "field2"],             // Secondary content fields
        "metadata": ["field1", "field2"]                // Metadata fields
    }},
    "field_types": {{
        "field_name": "html|text|list|object"          // Type of each field
    }},
    "recommendations": "Brief explanation of how to convert to Markdown"
}}"""
    
    def _build_converter_generation_prompt(self, content_analysis: Dict[str, Any], sample_json: Dict[str, Any], retry: bool = False) -> str:
        analysis_json = json.dumps(content_analysis, indent=2, ensure_ascii=False)
        sample_json_str = json.dumps(sample_json, indent=2, ensure_ascii=False)
        
        # Use regular string concatenation to avoid issues with triple quotes in f-strings
        prompt = """Generate Python code to convert JSON extraction results to Markdown format.

Content Analysis:
{analysis_json}

Sample JSON Structure:
{sample_json_str}

CRITICAL INTERFACE REQUIREMENTS (MUST BE STRICTLY FOLLOWED):
===========================================================

1. CLASS DEFINITION (MANDATORY):
   - MUST define a class named exactly 'MarkdownConverter' (case-sensitive)
   - MUST have __init__ method with EXACT signature:
     def __init__(self) -> None:
   - No parameters required for __init__

2. CONVERT METHOD (MANDATORY):
   - MUST have a method named exactly 'convert' (NOT convert_to_markdown, convert_json, etc.)
   - Method signature MUST be EXACTLY:
     def convert(self, json_data: Dict[str, Any]) -> str:
   - Parameter name MUST be exactly 'json_data' (not 'data', not 'json', not 'input_data', etc.)
   - Parameter type MUST be Dict[str, Any]
   - Return type annotation MUST be: -> str
   - Return value MUST be a plain string (NOT list, NOT dict, NOT other types)
   - The string MUST be valid Markdown format

3. IMPLEMENTATION REQUIREMENTS:
   - Follow Markdown syntax strictly:
     * Use # for H1, ## for H2, ### for H3, etc.
     * Use **bold** for bold text, *italic* for italic
     * Use - or * for unordered lists, 1. for ordered lists
     * Use [text](url) for links
     * Use > for blockquotes
     * Use `code` for inline code, ```code``` for code blocks
     * Use --- for horizontal rules
     * Properly escape special Markdown characters
   - Handle different content types:
     * HTML content: Convert HTML to Markdown (strip HTML tags, preserve structure)
     * Plain text: Use as-is with proper Markdown formatting
     * Lists: Convert to Markdown lists
     * Nested structures: Handle appropriately
   - Include proper error handling (try-except blocks)
   - Preserve content hierarchy (title, metadata, body, etc.)
   - Clean HTML tags and convert to Markdown equivalents:
     * <h1>-<h6> -> # - ######
     * <p> -> paragraph (blank line)
     * <strong>, <b> -> **bold**
     * <em>, <i> -> *italic*
     * <a href="..."> -> [text](url)
     * <ul>/<ol>/<li> -> Markdown lists
     * <code> -> `code`
     * <blockquote> -> > quote
     * <img> -> ![alt](src)
     * Strip other HTML tags but preserve text content

4. FORBIDDEN:
   - DO NOT create methods named convert_to_markdown, convert_json, convert_file, etc.
   - DO NOT use different parameter names (data, json, input_data, etc.)
   - DO NOT return list, dict, or other types - MUST return str
   - DO NOT create wrapper functions or alternative interfaces

5. CODE QUALITY REQUIREMENTS:
   - Code MUST be syntactically correct Python (no syntax errors)
   - All f-strings MUST be properly closed with matching quotes
   - All function definitions MUST be complete
   - All string literals MUST be properly terminated
   - Use triple quotes for multi-line strings when needed
   - Escape special characters properly in f-strings
   - Test that code can be compiled with compile(code, '<string>', 'exec') before returning
   - CRITICAL: If using f-strings with newlines, use triple-quoted f-strings (triple quotes) instead of single quotes with newline escapes
   - CRITICAL: Never use unterminated f-strings - always close them properly with matching quotes
   - CRITICAL: For multi-line strings in f-strings, prefer triple-quoted f-strings over single quotes with escape sequences

EXAMPLE INTERFACE (MUST FOLLOW THIS EXACT STRUCTURE):
```python
from typing import Dict, Any

class MarkdownConverter:
    def __init__(self) -> None:
        # Initialization if needed
        pass
    
    def convert(self, json_data: Dict[str, Any]) -> str:
        # Convert JSON to Markdown
        # Must return str (Markdown formatted string)
        markdown = ""
        # ... conversion logic ...
        return markdown
```

Generate complete, production-ready Python code with all necessary imports.
The code should be reusable, handle edge cases gracefully, and MUST be syntactically valid Python.
MUST strictly follow the interface specification above.""".format(
            analysis_json=analysis_json,
            sample_json_str=sample_json_str
        )
        
        if retry:
            # Add extra emphasis on syntax correctness for retry
            retry_warning = """

⚠️ RETRY MODE - PREVIOUS ATTEMPT HAD SYNTAX ERRORS ⚠️
===========================================================
CRITICAL SYNTAX REQUIREMENTS (MUST FOLLOW):
1. ALL f-strings MUST be properly closed:
   - WRONG: return f" (unterminated string)
   - CORRECT: return f"..." or return f'''...'''
2. For multi-line f-strings, ALWAYS use triple quotes:
   - WRONG: f"..." with escape sequences
   - CORRECT: f'''...''' with actual newlines
3. NEVER leave f-strings unterminated
4. Test your code mentally - every opening quote MUST have a closing quote
5. If you're unsure, use regular strings with .format() or % formatting instead of f-strings

The previous code had syntax errors. Please be EXTREMELY careful with string quotes and f-string syntax.
"""
            prompt = prompt + retry_warning
        
        return prompt
