import json
import logging
from typing import List, Dict, Any
from openai import OpenAI
from config import Settings

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Main orchestrator agent that coordinates multiple agents
    to analyze HTML files and generate extraction code
    """
    
    def __init__(self):
        self.client = OpenAI(
            api_key=Settings.OPENAI_API_KEY,
            base_url=Settings.OPENAI_BASE_URL
        )
        self.model = Settings.OPENAI_MODEL
        
    def coordinate_analysis(self, html_files: List[str], analysis_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Coordinate the analysis process and synthesize results
        """
        prompt = self._build_coordination_prompt(html_files, analysis_results)
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        
        # Handle response - should be a ChatCompletion object
        if hasattr(response, 'choices') and len(response.choices) > 0:
            result = response.choices[0].message.content
        else:
            logger.error(f"Unexpected response format: {type(response)}")
            return {"error": f"Unexpected response format: {type(response)}"}
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON, returning raw result")
            return {"raw_result": result}
    
    def generate_final_schema(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate final JSON schema based on all analysis results
        """
        prompt = self._build_schema_generation_prompt(analysis_data)
        
        try:
            # Try with response_format first (may not be supported by custom endpoints)
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self._get_schema_system_prompt()},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.2,
                    response_format={"type": "json_object"}
                )
            except Exception as e:
                # If response_format is not supported, try without it
                logger.warning(f"response_format not supported, retrying without it: {e}")
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self._get_schema_system_prompt()},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.2
                )
            
            # Handle response
            if hasattr(response, 'choices') and len(response.choices) > 0:
                result = response.choices[0].message.content
            else:
                logger.error(f"Unexpected response format: {type(response)}")
                return {"error": f"Unexpected response format: {type(response)}"}
            
            # Try to parse JSON
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code blocks
                import re
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', result, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(1))
                # Try to extract JSON directly
                json_match = re.search(r'\{.*\}', result, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(0))
                logger.warning("Failed to parse JSON, returning raw result")
                return {"raw_result": result, "error": "Failed to parse JSON"}
        except Exception as e:
            logger.error(f"Error generating schema: {e}")
            return {"error": str(e)}
    
    def _get_system_prompt(self) -> str:
        return """You are an orchestrator agent coordinating multiple AI agents to analyze HTML structures.
Your role is to synthesize analysis results from different agents and make final decisions.
You should identify common patterns across multiple HTML files and create a unified understanding."""
    
    def _get_schema_system_prompt(self) -> str:
        return """You are generating a JSON schema that represents the structure of HTML content.
The schema should include:
1. XPath paths to key content sections
2. Descriptions of what each section represents (e.g., "comments", "article body", "title")
3. Patterns that identify similar elements
4. Metadata about the structure

Output must be valid JSON."""
    
    def _build_coordination_prompt(self, html_files: List[str], analysis_results: Dict[str, Any]) -> str:
        return f"""Analyze the following HTML files and their analysis results:

HTML Files: {', '.join(html_files)}

Analysis Results:
{json.dumps(analysis_results, indent=2, ensure_ascii=False)}

Please synthesize these results and identify:
1. Common structural patterns across all files
2. Key content sections (title, body, comments, etc.)
3. XPath patterns that work across multiple files
4. Any inconsistencies or edge cases

Return your analysis as JSON with the following structure:
{{
    "common_patterns": [...],
    "content_sections": [...],
    "xpath_patterns": [...],
    "inconsistencies": [...]
}}"""
    
    def _build_schema_generation_prompt(self, analysis_data: Dict[str, Any]) -> str:
        return f"""Based on the following analysis data, generate a comprehensive JSON schema:

{json.dumps(analysis_data, indent=2, ensure_ascii=False)}

The schema should follow this structure:
{{
    "schema_version": "1.0",
    "description": "Schema for extracting content from HTML pages",
    "sections": [
        {{
            "name": "section_name",
            "description": "What this section represents (e.g., 'comments', 'article body')",
            "xpath": "xpath_expression",
            "xpath_list": ["xpath1", "xpath2", ...],
            "is_list": true/false,
            "attributes": {{"key": "value"}},
            "notes": "Additional notes"
        }}
    ],
    "metadata": {{
        "total_sections": number,
        "extraction_notes": "..."
    }}
}}

Ensure all XPath expressions are valid and can extract the intended content."""

