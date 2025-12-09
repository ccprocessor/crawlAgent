"""
Prompt templates for different agents
"""


class PromptTemplates:
    """
    Centralized prompt templates for all agents
    """
    
    @staticmethod
    def get_orchestrator_prompt(html_files: list, analysis_results: dict) -> str:
        """
        Prompt for orchestrator to synthesize analysis results
        """
        return f"""You are coordinating multiple AI agents to analyze HTML structures.

HTML Files Analyzed: {len(html_files)}
Files: {', '.join(html_files)}

Analysis Results from Multiple Agents:
{analysis_results}

Your task:
1. Synthesize all analysis results
2. Identify common patterns across all HTML files
3. Create a unified understanding of the structure
4. Generate a comprehensive JSON schema

Focus on:
- Common XPath patterns that work across multiple files
- Content sections that appear consistently
- Edge cases and variations
- Best extraction strategies

Return a structured analysis in JSON format."""
    
    @staticmethod
    def get_analyzer_prompt(html_content: str, file_path: str) -> str:
        """
        Prompt for analyzer agent
        """
        return f"""Analyze this HTML file and identify all content sections.

File: {file_path}

HTML Content (first 50000 chars):
{html_content[:50000]}

Identify:
1. Title/Heading sections
2. Main body content
3. Comments sections (if any)
4. Metadata (author, date, tags, etc.)
5. Navigation elements
6. Any other significant content sections

For each section, provide:
- XPath expression
- Description
- Content type
- Whether it's a list/collection
- Sample content

Return JSON format."""
    
    @staticmethod
    def get_visual_analyzer_prompt(file_path: str) -> str:
        """
        Prompt for visual analyzer
        """
        return f"""Analyze the visual structure of this rendered HTML page.

File: {file_path}

Identify:
- Visual layout structure
- Content sections based on visual appearance
- Repeating patterns (comments, list items, etc.)
- Visual hierarchy
- Styling patterns that indicate content types

Return JSON with visual analysis."""
    
    @staticmethod
    def get_schema_generation_prompt(analysis_data: dict) -> str:
        """
        Prompt for generating final JSON schema
        """
        return f"""Generate a comprehensive JSON schema for HTML content extraction.

Based on analysis data:
{analysis_data}

Create a schema with:
- Section definitions
- XPath expressions
- Descriptions
- Metadata

Schema should be:
- Complete (covers all content sections)
- Accurate (XPath expressions work)
- Well-documented
- Reusable across similar HTML structures

Return valid JSON schema."""
    
    @staticmethod
    def get_code_generation_prompt(json_schema: dict, language: str = 'python') -> str:
        """
        Prompt for code generator
        """
        return f"""Generate production-ready {language} code for HTML content extraction.

JSON Schema:
{json_schema}

Requirements:
- Robust error handling
- Clean, maintainable code
- Well-documented
- Handles edge cases
- Returns structured data
- Supports batch processing

Generate complete, runnable code."""

