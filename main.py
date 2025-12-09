#!/usr/bin/env python3
"""
Main entry point for HTML Agent Analysis System
"""
import os
import json
import logging
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional
from config import Settings

from agents import Orchestrator, AnalyzerAgent, CodeGeneratorAgent, CodeValidatorAgent, MarkdownConverterAgent
from utils import HTMLParser, VisualAnalyzer, URLDownloader
from utils.logger import setup_logging
from utils.checkpoint import CheckpointManager

# Setup beautiful logging
logger = setup_logging(log_dir="logs", level=Settings.LOG_LEVEL)


class HTMLAgentSystem:
    """
    Main system that coordinates all agents for HTML analysis
    """
    
    def __init__(self):
        # Validate settings
        try:
            Settings.validate()
        except ValueError as e:
            logger.error(f"Configuration error: {e}")
            raise
        
        self.orchestrator = Orchestrator()
        self.analyzer = AnalyzerAgent()
        self.code_generator = CodeGeneratorAgent()
        self.visual_analyzer = VisualAnalyzer()
        self.code_validator = CodeValidatorAgent()
        self.markdown_converter = MarkdownConverterAgent()
        self.output_dir = Path(Settings.OUTPUT_DIR)
        self.output_dir.mkdir(exist_ok=True)
        self.checkpoint = CheckpointManager(self.output_dir)
    
    def process_input(self, input_path: str, use_visual: bool = True, resume: bool = True) -> Dict[str, Any]:
        """
        Process input - can be a directory or URL list file
        """
        input_path_obj = Path(input_path)
        
        # Note: Checkpoints are now managed per step, not globally
        # Each step creates its own flow directory and checkpoint
        
        # Check if it's a file (URL list) or directory
        if input_path_obj.is_file():
            logger.info(f"Processing URL list file: {input_path}")
            return self._process_url_list(input_path, use_visual, resume)
        elif input_path_obj.is_dir():
            logger.info(f"Processing HTML directory: {input_path}")
            return self._process_directory(input_path, use_visual, resume)
        else:
            logger.error(f"Input path does not exist: {input_path}")
            return {"error": f"Input path does not exist: {input_path}"}
    
    def _process_directory(self, html_directory: str, use_visual: bool = True, resume: bool = True) -> Dict[str, Any]:
        """
        Process a directory of HTML files and generate extraction code
        """
        # Step 1: Load HTML files
        html_files = HTMLParser.load_html_files(html_directory)
        if not html_files:
            logger.error("No HTML files found in directory")
            return {"error": "No HTML files found"}
        
        logger.info(f"Found {len(html_files)} HTML files")
        return self._process_html_files(html_files, use_visual, resume)
    
    def _process_url_list(self, url_file: str, use_visual: bool = True, resume: bool = True) -> Dict[str, Any]:
        """
        Process URLs from a file and generate extraction code
        Note: This method should only be called when URL file is provided as custom input.
        For typical/spread directories, HTML files should be pre-downloaded to their html/ directories.
        """
        # This method is kept for backward compatibility with custom URL files
        # In normal workflow, URLs should be pre-downloaded to input/html directories
        logger.warning("Processing URL file directly. Consider pre-downloading HTML files to input directories.")
        
        # Step 1: Load URLs
        urls = URLDownloader.load_urls_from_file(url_file)
        if not urls:
            logger.error("No valid URLs found in file")
            return {"error": "No valid URLs found"}
        
        logger.info(f"Found {len(urls)} URLs")
        
        # For custom URL files, download to a temporary directory in output
        # (This is a fallback for custom inputs, not the normal workflow)
        html_dir = self.output_dir / 'downloaded_html'
        if resume and html_dir.exists() and any(html_dir.iterdir()):
            logger.info("Using existing downloaded HTML files")
            html_files = HTMLParser.load_html_files(str(html_dir))
            if html_files:
                # Add URL info if missing
                for i, html_file in enumerate(html_files):
                    if 'url' not in html_file and i < len(urls):
                        html_file['url'] = urls[i]
        else:
            logger.info("Downloading HTML content from URLs...")
            html_files = URLDownloader.download_multiple_urls(urls, output_dir=str(self.output_dir))
            
            if not html_files:
                logger.error("Failed to download any HTML content")
                return {"error": "Failed to download HTML content"}
            
            logger.info(f"Successfully downloaded {len(html_files)} HTML files")
        
        return self._process_html_files(html_files, use_visual, resume)
    
    def _execute_extraction_code(self, code_path: Path, output_dir: Path, json_schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Execute the generated extraction code on spread directory
        
        REQUIRED CODE INTERFACE SPECIFICATION:
        ======================================
        The generated code MUST strictly follow this interface:
        
        1. Class Definition:
           - MUST define a class named 'HTMLExtractor'
           - MUST have __init__ method with signature: __init__(self, schema: Dict[str, Any], logger: Optional[logging.Logger] = None)
           - schema parameter MUST accept the JSON schema dictionary
           
        2. Extract Method:
           - MUST have a method named 'extract' (NOT extract_from_string, extract_from_file, etc.)
           - Method signature MUST be: extract(self, html_content: Optional[str] = None, file_path: Optional[str] = None) -> Dict[str, Any]
           - Parameter names MUST be exactly: 'html_content' and 'file_path' (no variations)
           - Return type MUST be Dict[str, Any] (NOT ExtractionResult, NOT list, NOT other types)
           - The method MUST return a plain dictionary with section names as keys
           
        3. Input/Output:
           - Input: html_content (str) OR file_path (str), at least one must be provided
           - Output: Dict[str, Any] with extracted data, keys are section names from schema
           
        4. Schema Constant (Optional but Recommended):
           - MAY define SCHEMA constant at module level: SCHEMA: Dict[str, Any] = {...}
           - If defined, should match the schema passed to __init__
        
        Example interface:
        ```python
        class HTMLExtractor:
            def __init__(self, schema: Dict[str, Any], logger: Optional[logging.Logger] = None) -> None:
                self.schema = schema
                # ... initialization ...
            
            def extract(self, html_content: Optional[str] = None, file_path: Optional[str] = None) -> Dict[str, Any]:
                # Extract content and return Dict[str, Any]
                return {"section1": value1, "section2": value2, ...}
        ```
        """
        import importlib.util
        import sys
        from typing import Optional
        
        # Check spread directory for HTML files or URLs
        spread_html_dir = Settings.SPREAD_HTML_DIR
        spread_urls_file = Settings.SPREAD_URLS_FILE
        
        html_files_to_process = []
        
        # Check if HTML files exist
        if spread_html_dir.exists() and any(spread_html_dir.iterdir()):
            # Load existing HTML files
            html_files = HTMLParser.load_html_files(str(spread_html_dir))
            html_files_to_process = html_files
            logger.info(f"Found {len(html_files_to_process)} HTML files in spread/html directory")
        elif spread_urls_file.exists():
            # Download HTML files from URLs
            logger.info(f"No HTML files in spread/html, downloading from {spread_urls_file}...")
            logger.info(f"Using spread URLs file: {spread_urls_file}")
            urls = URLDownloader.load_urls_from_file(str(spread_urls_file))
            if not urls:
                logger.warning(f"No valid URLs found in {spread_urls_file}")
                return None
            
            # Download to spread/html directory
            spread_html_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Downloading {len(urls)} URLs to {spread_html_dir}...")
            html_files = URLDownloader.download_multiple_urls(urls, output_dir=str(spread_html_dir))
            
            if not html_files:
                logger.warning("Failed to download HTML files from URLs")
                return None
            
            html_files_to_process = html_files
            logger.info(f"Downloaded {len(html_files_to_process)} HTML files to spread/html")
        else:
            logger.warning("No HTML files or urls.txt found in spread directory")
            return None
        
        if not html_files_to_process:
            logger.warning("No HTML files to process")
            return None
        
        # Load and execute the generated code
        try:
            # Load the extraction code module
            spec = importlib.util.spec_from_file_location("extraction_code", code_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Failed to load extraction code from {code_path}")
            
            extraction_module = importlib.util.module_from_spec(spec)
            sys.modules['extraction_code'] = extraction_module
            spec.loader.exec_module(extraction_module)
            
            # Strictly follow the required interface
            # 1. Must have HTMLExtractor class
            if not hasattr(extraction_module, 'HTMLExtractor'):
                raise ValueError("Generated code MUST define 'HTMLExtractor' class. Found classes: " + 
                               str([name for name in dir(extraction_module) if isinstance(getattr(extraction_module, name, None), type)]))
            
            # 2. Must have schema parameter in __init__
            import inspect
            init_signature = inspect.signature(extraction_module.HTMLExtractor.__init__)
            init_params = list(init_signature.parameters.keys())
            
            if 'schema' not in init_params:
                raise ValueError(f"HTMLExtractor.__init__ MUST accept 'schema' parameter. Found parameters: {init_params}")
            
            # 3. Get schema (prefer module SCHEMA constant, fallback to passed schema)
            if hasattr(extraction_module, 'SCHEMA'):
                schema_to_use = extraction_module.SCHEMA
            else:
                schema_to_use = json_schema
            
            # 4. Instantiate extractor with schema
            extractor = extraction_module.HTMLExtractor(schema=schema_to_use)
            
            # 5. Must have extract method (exact name, not extract_from_string, etc.)
            if not hasattr(extractor, 'extract'):
                available_methods = [name for name in dir(extractor) if not name.startswith('_') and callable(getattr(extractor, name))]
                raise ValueError(f"HTMLExtractor MUST have 'extract' method. Found methods: {available_methods}")
            
            # 6. Verify extract method signature
            extract_method = getattr(extractor, 'extract')
            extract_sig = inspect.signature(extract_method)
            extract_params = list(extract_sig.parameters.keys())
            
            # Must have html_content or file_path parameter
            if 'html_content' not in extract_params and 'file_path' not in extract_params:
                raise ValueError(f"extract() method MUST accept 'html_content' or 'file_path' parameter. Found parameters: {extract_params}")
            
            # Must return Dict[str, Any]
            if extract_sig.return_annotation == inspect.Signature.empty:
                raise ValueError("extract() method MUST have return type annotation: -> Dict[str, Any]")
            
            return_type_str = str(extract_sig.return_annotation)
            if 'Dict' not in return_type_str and 'dict' not in return_type_str.lower():
                raise ValueError(f"extract() method MUST return Dict[str, Any]. Found return type: {return_type_str}")
            
            extract_func = extract_method
            
            # Create results directory for extraction results
            results_dir = output_dir / 'extraction_results'
            results_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created results directory: {results_dir}")
            
            # Process each HTML file and save individual JSON files
            results_summary = []
            processed_count = 0
            failed_count = 0
            
            for html_file in html_files_to_process:
                html_content = html_file.get('content', '')
                file_path = html_file.get('path', '')
                file_name = html_file.get('name', 'unknown')
                
                if not html_content and file_path:
                    # Try to read from file
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            html_content = f.read()
                    except Exception as e:
                        logger.warning(f"Failed to read {file_path}: {e}")
                        failed_count += 1
                        results_summary.append({
                            'file': file_name,
                            'path': file_path,
                            'status': 'failed',
                            'error': f"Failed to read file: {str(e)}"
                        })
                        continue
                
                if not html_content:
                    logger.warning(f"No HTML content for {file_name}")
                    failed_count += 1
                    results_summary.append({
                        'file': file_name,
                        'path': file_path,
                        'status': 'failed',
                        'error': 'No HTML content available'
                    })
                    continue
                
                try:
                    # Extract content using the generated code
                    # Strictly follow the interface: extract(html_content=..., file_path=...)
                    if html_content:
                        result = extractor.extract(html_content=html_content)
                    elif file_path:
                        result = extractor.extract(file_path=file_path)
                    else:
                        raise ValueError("Either html_content or file_path must be provided")
                    
                    # Result must be Dict[str, Any]
                    if not isinstance(result, dict):
                        raise TypeError(f"extract() method MUST return Dict[str, Any], got {type(result)}")
                    
                    # Generate JSON filename from HTML filename
                    # Remove .html extension and add .json
                    json_filename = file_name.rsplit('.html', 1)[0] if file_name.endswith('.html') else file_name
                    json_filename = json_filename.rsplit('.htm', 1)[0] if json_filename.endswith('.htm') else json_filename
                    json_filename = f"{json_filename}.json"
                    
                    # Clean filename to remove invalid characters
                    import re
                    json_filename = re.sub(r'[^\w\-_\.]', '_', json_filename)
                    
                    # Save individual result JSON file to results directory
                    individual_result_path = results_dir / json_filename
                    with open(individual_result_path, 'w', encoding='utf-8') as f:
                        json.dump(result, f, indent=2, ensure_ascii=False)
                    
                    logger.info(f"Successfully extracted and saved result for {file_name} to extraction_results/{json_filename}")
                    
                    processed_count += 1
                    results_summary.append({
                        'file': file_name,
                        'path': file_path,
                        'status': 'success',
                        'result_file': json_filename
                    })
                except Exception as e:
                    logger.error(f"Failed to extract content from {file_name}: {e}")
                    failed_count += 1
                    results_summary.append({
                        'file': file_name,
                        'path': file_path,
                        'status': 'failed',
                        'error': str(e)
                    })
            
            # Save summary file with all results (in flow5 directory, not in results folder)
            summary_path = output_dir / 'extraction_results_summary.json'
            with open(summary_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'total_files': len(html_files_to_process),
                    'processed_files': processed_count,
                    'failed_files': failed_count,
                    'results_directory': 'extraction_results',
                    'results': results_summary
                }, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Extraction summary saved to {summary_path}")
            logger.info(f"Generated {processed_count} individual result JSON files in extraction_results/ directory")
            
            return {
                'processed_count': processed_count,
                'failed_count': failed_count,
                'results_directory': str(results_dir),
                'summary_path': str(summary_path),
                'individual_files': processed_count
            }
            
        except Exception as e:
            logger.error(f"Failed to execute extraction code: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def _fix_markdown_converter_syntax(self, code: str, syntax_error: SyntaxError) -> str:
        """
        Attempt to fix common syntax errors in generated markdown converter code
        """
        import re
        
        lines = code.split('\n')
        error_line_num = syntax_error.lineno - 1 if syntax_error.lineno and syntax_error.lineno <= len(lines) else len(lines) - 1
        
        if error_line_num < len(lines):
            error_line = lines[error_line_num]
            
            # Fix unterminated f-strings
            if 'f"' in error_line or "f'" in error_line or 'f"""' in error_line or "f'''" in error_line:
                # Check for triple-quoted f-strings first
                if 'f"""' in error_line:
                    # Find the start of the f-string
                    f_start = error_line.find('f"""')
                    if f_start != -1:
                        # Check if it's closed on the same line
                        remaining = error_line[f_start + 4:]
                        if '"""' not in remaining:
                            # Not closed, need to find where it should end
                            # Look ahead for closing triple quotes
                            found_close = False
                            for i in range(error_line_num + 1, min(error_line_num + 20, len(lines))):
                                if '"""' in lines[i]:
                                    found_close = True
                                    break
                            
                            if not found_close:
                                # Add closing triple quotes at end of current line or next logical place
                                # If line ends with newline escape, it's probably a multi-line string
                                if error_line.rstrip().endswith('\\n') or error_line.rstrip().endswith('\\'):
                                    # Convert to proper multi-line f-string or add closing
                                    # Try to find a good place to close it
                                    if error_line_num + 1 < len(lines):
                                        next_line = lines[error_line_num + 1]
                                        # If next line is part of the string content, we need to close after it
                                        if next_line.strip() and not next_line.strip().startswith('"""'):
                                            # Look for where the string should end
                                            # Common pattern: f"""\n{content}\n"""
                                            # Find the next non-indented line or closing pattern
                                            for i in range(error_line_num + 1, min(error_line_num + 10, len(lines))):
                                                if lines[i].strip() and not lines[i].startswith(' ') and not lines[i].startswith('\t'):
                                                    # Found next statement, close before it
                                                    lines[i-1] = lines[i-1].rstrip() + '"""'
                                                    break
                                            else:
                                                # No clear end, close at end of next line
                                                if error_line_num + 1 < len(lines):
                                                    lines[error_line_num + 1] = lines[error_line_num + 1].rstrip() + '"""'
                                                else:
                                                    lines[error_line_num] = error_line.rstrip() + '"""'
                                        else:
                                            # Already has closing, might be a different issue
                                            pass
                                    else:
                                        lines[error_line_num] = error_line.rstrip() + '"""'
                                else:
                                    # Simple case, just add closing
                                    lines[error_line_num] = error_line.rstrip() + '"""'
                
                elif "f'''" in error_line:
                    # Similar logic for triple single quotes
                    f_start = error_line.find("f'''")
                    if f_start != -1:
                        remaining = error_line[f_start + 4:]
                        if "'''" not in remaining:
                            found_close = False
                            for i in range(error_line_num + 1, min(error_line_num + 20, len(lines))):
                                if "'''" in lines[i]:
                                    found_close = True
                                    break
                            
                            if not found_close:
                                if error_line.rstrip().endswith('\\n') or error_line.rstrip().endswith('\\'):
                                    if error_line_num + 1 < len(lines):
                                        next_line = lines[error_line_num + 1]
                                        if next_line.strip() and not next_line.strip().startswith("'''"):
                                            for i in range(error_line_num + 1, min(error_line_num + 10, len(lines))):
                                                if lines[i].strip() and not lines[i].startswith(' ') and not lines[i].startswith('\t'):
                                                    lines[i-1] = lines[i-1].rstrip() + "'''"
                                                    break
                                            else:
                                                if error_line_num + 1 < len(lines):
                                                    lines[error_line_num + 1] = lines[error_line_num + 1].rstrip() + "'''"
                                                else:
                                                    lines[error_line_num] = error_line.rstrip() + "'''"
                                    else:
                                        lines[error_line_num] = error_line.rstrip() + "'''"
                                else:
                                    lines[error_line_num] = error_line.rstrip() + "'''"
                
                # Fix regular f-strings (f" or f')
                elif 'f"' in error_line or "f'" in error_line:
                    # Check if f-string is not properly closed
                    f_string_pattern = r'f["\']'
                    matches = list(re.finditer(f_string_pattern, error_line))
                    
                    if matches:
                        last_match = matches[-1]
                        quote_char = error_line[last_match.end() - 1]
                        remaining = error_line[last_match.end():]
                        
                        # Count quotes in remaining part
                        quote_count = remaining.count(quote_char)
                        # Count escaped quotes
                        escaped_quotes = remaining.count('\\' + quote_char)
                        # Actual unescaped quotes
                        unescaped_quotes = quote_count - escaped_quotes
                        
                        # If odd number of unescaped quotes, string is not closed
                        if unescaped_quotes % 2 == 0:  # Even means not closed (opening quote not counted)
                            # Check if line ends without closing quote
                            if not error_line.rstrip().endswith(quote_char):
                                # Check if next line might be continuation
                                if error_line_num + 1 < len(lines):
                                    next_line = lines[error_line_num + 1]
                                    # If next line is indented and has content, might be part of the string
                                    if next_line.strip() and (next_line.startswith(' ') or next_line.startswith('\t')):
                                        # This is likely a multi-line string that should use triple quotes
                                        # Convert to triple-quoted f-string
                                        # Find the opening f"
                                        f_pos = error_line.find('f"')
                                        if f_pos != -1:
                                            # Replace f" with f""" and find where to close
                                            lines[error_line_num] = error_line[:f_pos+1] + '"""' + error_line[f_pos+2:]
                                            # Find where to close (next non-indented line or end of block)
                                            for i in range(error_line_num + 1, min(error_line_num + 15, len(lines))):
                                                if lines[i].strip() and not (lines[i].startswith(' ') or lines[i].startswith('\t')):
                                                    # Found next statement, close before it
                                                    lines[i-1] = lines[i-1].rstrip() + '"""'
                                                    break
                                            else:
                                                # No clear end, close at end of next line
                                                if error_line_num + 1 < len(lines):
                                                    lines[error_line_num + 1] = lines[error_line_num + 1].rstrip() + '"""'
                                    else:
                                        # Add closing quote
                                        lines[error_line_num] = error_line.rstrip() + quote_char
                                else:
                                    # Add closing quote at end
                                    lines[error_line_num] = error_line.rstrip() + quote_char
        
        fixed_code = '\n'.join(lines)
        
        # Additional fixes for common issues
        # Fix incomplete triple-quoted strings in f-strings (more aggressive)
        # Look for patterns like f"""\n without closing
        fixed_code = re.sub(r'(f"""[^"]*?)(\n)(?![^"]*""")', r'\1\2"""', fixed_code, flags=re.MULTILINE | re.DOTALL)
        fixed_code = re.sub(r"(f'''[^']*?)(\n)(?![^']*''')", r"\1\2'''", fixed_code, flags=re.MULTILINE | re.DOTALL)
        
        return fixed_code
    
    def _execute_markdown_conversion(self, converter_code_path: Path, json_results_dir: Path, output_dir: Path) -> Optional[Dict[str, Any]]:
        """
        Execute the markdown converter code on JSON results
        """
        import importlib.util
        import sys
        
        if not converter_code_path.exists():
            logger.error(f"Markdown converter code not found: {converter_code_path}")
            return None
        
        if not json_results_dir.exists():
            logger.error(f"JSON results directory not found: {json_results_dir}")
            return None
        
        # Load all JSON files
        json_files = list(json_results_dir.glob('*.json'))
        if not json_files:
            logger.warning("No JSON files found to convert")
            return None
        
        # Load and execute the converter code
        try:
            # Load the converter code module
            spec = importlib.util.spec_from_file_location("markdown_converter", converter_code_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Failed to load markdown converter code from {converter_code_path}")
            
            converter_module = importlib.util.module_from_spec(spec)
            sys.modules['markdown_converter'] = converter_module
            spec.loader.exec_module(converter_module)
            
            # Strictly follow the required interface
            # 1. Must have MarkdownConverter class
            if not hasattr(converter_module, 'MarkdownConverter'):
                raise ValueError("Generated code MUST define 'MarkdownConverter' class. Found classes: " + 
                               str([name for name in dir(converter_module) if isinstance(getattr(converter_module, name, None), type)]))
            
            # 2. Verify __init__ signature (should have no required parameters)
            import inspect
            init_signature = inspect.signature(converter_module.MarkdownConverter.__init__)
            init_params = [p for p in init_signature.parameters.keys() if p != 'self']
            if init_params:
                # Check if all params have defaults
                for param_name in init_params:
                    param = init_signature.parameters[param_name]
                    if param.default == inspect.Parameter.empty:
                        raise ValueError(f"MarkdownConverter.__init__() MUST have no required parameters. Found: {init_params}")
            
            # 3. Instantiate converter
            converter = converter_module.MarkdownConverter()
            
            # 4. Must have convert method (exact name)
            if not hasattr(converter, 'convert'):
                available_methods = [name for name in dir(converter) if not name.startswith('_') and callable(getattr(converter, name))]
                raise ValueError(f"MarkdownConverter MUST have 'convert' method. Found methods: {available_methods}")
            
            # 5. Verify convert method signature
            convert_method = getattr(converter, 'convert')
            convert_sig = inspect.signature(convert_method)
            convert_params = list(convert_sig.parameters.keys())
            
            # Must have json_data parameter
            if 'json_data' not in convert_params:
                raise ValueError(f"convert() method MUST accept 'json_data' parameter. Found parameters: {convert_params}")
            
            # Must return str
            if convert_sig.return_annotation == inspect.Signature.empty:
                raise ValueError("convert() method MUST have return type annotation: -> str")
            
            return_type_str = str(convert_sig.return_annotation)
            if 'str' not in return_type_str.lower() or 'str' != return_type_str.strip():
                # Allow Optional[str] or Union[str, ...] but must include str
                if 'str' not in return_type_str:
                    raise ValueError(f"convert() method MUST return str. Found return type: {return_type_str}")
            
            # Create markdown output directory
            markdown_output_dir = output_dir / 'markdown_output'
            markdown_output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created markdown output directory: {markdown_output_dir}")
            
            # Process each JSON file
            processed_count = 0
            failed_count = 0
            results_summary = []
            
            for json_file in json_files:
                try:
                    # Load JSON
                    with open(json_file, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)
                    
                    # Convert to Markdown
                    # Strictly follow the interface: convert(json_data=...)
                    markdown_content = converter.convert(json_data=json_data)
                    
                    # Result must be str
                    if not isinstance(markdown_content, str):
                        raise TypeError(f"convert() method MUST return str, got {type(markdown_content)}")
                    
                    # Generate markdown filename
                    markdown_filename = json_file.stem + '.md'
                    markdown_path = markdown_output_dir / markdown_filename
                    
                    # Save Markdown file
                    with open(markdown_path, 'w', encoding='utf-8') as f:
                        f.write(markdown_content)
                    
                    logger.info(f"Successfully converted {json_file.name} to {markdown_filename}")
                    processed_count += 1
                    results_summary.append({
                        'json_file': json_file.name,
                        'markdown_file': markdown_filename,
                        'status': 'success'
                    })
                except Exception as e:
                    logger.error(f"Failed to convert {json_file.name}: {e}")
                    failed_count += 1
                    results_summary.append({
                        'json_file': json_file.name,
                        'status': 'failed',
                        'error': str(e)
                    })
            
            # Save summary
            summary_path = output_dir / 'markdown_conversion_summary.json'
            with open(summary_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'total_files': len(json_files),
                    'processed_files': processed_count,
                    'failed_files': failed_count,
                    'markdown_output_directory': 'markdown_output',
                    'results': results_summary
                }, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Markdown conversion summary saved to {summary_path}")
            logger.info(f"Generated {processed_count} Markdown files in markdown_output/ directory")
            
            return {
                'processed_count': processed_count,
                'failed_count': failed_count,
                'markdown_output_directory': str(markdown_output_dir),
                'summary_path': str(summary_path)
            }
            
        except Exception as e:
            logger.error(f"Failed to execute markdown conversion: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def _process_html_files(self, html_files: List[Dict[str, str]], use_visual: bool = True, resume: bool = True) -> Dict[str, Any]:
        """
        Process HTML files and generate extraction code with checkpoint support
        Each step creates a new flow directory
        """
        file_identifiers = [f.get('url', f.get('path', 'unknown')) for f in html_files]
        
        # Initialize variables
        analysis_results = None
        visual_results = None
        synthesized = None
        json_schema = None
        extraction_code = None
        
        # Load checkpoints from existing flow directories if resume is enabled
        # Track which steps have been completed based on checkpoints
        completed_steps = {}
        if resume:
            # Find all existing flow directories and load checkpoints
            existing_flows = []
            if Settings.OUTPUT_DIR.exists():
                for item in Settings.OUTPUT_DIR.iterdir():
                    if item.is_dir() and item.name.startswith('flow'):
                        try:
                            flow_num = int(item.name[4:])
                            checkpoint_manager = CheckpointManager(item)
                            checkpoint = checkpoint_manager.load_checkpoint()
                            if checkpoint:
                                step = checkpoint.get('step', 'unknown')
                                existing_flows.append({
                                    'flow_id': flow_num,
                                    'flow_dir': item,
                                    'checkpoint': checkpoint,
                                    'step': step
                                })
                                # Map step to flow_id for later use
                                if step == "text_analysis":
                                    completed_steps['step1'] = flow_num
                                elif step == "visual_analysis":
                                    completed_steps['step2'] = flow_num
                                elif step == "synthesized":
                                    completed_steps['step3'] = flow_num
                                elif step == "schema":
                                    completed_steps['step4'] = flow_num
                                elif step == "code":
                                    completed_steps['step5'] = flow_num
                        except (ValueError, Exception) as e:
                            logger.debug(f"Could not load checkpoint from {item.name}: {e}")
                            continue
            
            # Sort by flow_id to process in order
            existing_flows.sort(key=lambda x: x['flow_id'])
            
            # Load data from checkpoints in order (later checkpoints contain all previous data)
            for flow_info in existing_flows:
                checkpoint = flow_info['checkpoint']
                step = checkpoint.get('step')
                data = checkpoint.get('data', {})
                
                logger.info(f"Found checkpoint in {flow_info['flow_dir'].name}: step={step}")
                
                # Load data based on step (later steps contain all previous data)
                if step == "text_analysis":
                    analysis_results = data.get('analysis_results')
                    logger.info(f"Loaded text analysis results from {flow_info['flow_dir'].name}")
                elif step == "visual_analysis":
                    visual_results = data.get('visual_results')
                    analysis_results = data.get('analysis_results')  # Also load previous step data
                    logger.info(f"Loaded visual analysis results from {flow_info['flow_dir'].name}")
                elif step == "synthesized":
                    synthesized = data.get('synthesized')
                    analysis_results = data.get('analysis_results')
                    visual_results = data.get('visual_results')
                    logger.info(f"Loaded synthesized results from {flow_info['flow_dir'].name}")
                elif step == "schema":
                    json_schema = data.get('schema')
                    synthesized = data.get('synthesized')
                    analysis_results = data.get('analysis_results')
                    visual_results = data.get('visual_results')
                    logger.info(f"Loaded schema from {flow_info['flow_dir'].name}")
                elif step == "code_generated":
                    extraction_code = data.get('code')
                    json_schema = data.get('schema')
                    synthesized = data.get('synthesized')
                    analysis_results = data.get('analysis_results')
                    visual_results = data.get('visual_results')
                    logger.info(f"Loaded generated code from {flow_info['flow_dir'].name}")
                elif step == "code_validated" or step == "code":
                    extraction_code = data.get('code')
                    validation_result = data.get('validation')
                    json_schema = data.get('schema')
                    synthesized = data.get('synthesized')
                    analysis_results = data.get('analysis_results')
                    visual_results = data.get('visual_results')
                    logger.info(f"Loaded validated code from {flow_info['flow_dir'].name}")
            
            if existing_flows:
                logger.info(f"Resuming from checkpoints: found {len(existing_flows)} completed steps")
                logger.info(f"Completed steps: {list(completed_steps.keys())}")
        
        # Step 1: Analyze HTML files with analyzer agent
        # Check if we already have results from checkpoint
        if analysis_results is not None:
            logger.info("Step 1: Using text analysis results from checkpoint, skipping...")
            # Use existing flow directory from checkpoint
            step1_flow_id = completed_steps.get('step1', 1)
            step1_output_dir = Settings.get_flow_output_dir(step1_flow_id)
            step1_checkpoint = CheckpointManager(step1_output_dir)
        else:
            # Create new flow directory for this step
            step1_flow_id = Settings.get_next_flow_id()
            step1_output_dir = Settings.get_flow_output_dir(step1_flow_id)
            step1_checkpoint = CheckpointManager(step1_output_dir)
            
            # Check if step result exists, if yes, skip and load from file
            if step1_checkpoint.step_result_exists("step1_text_analysis"):
                logger.info("Step 1: Using cached text analysis results (file exists)")
                analysis_results = step1_checkpoint.load_step_result("step1_text_analysis")
                # Also load from checkpoint if available
                checkpoint = step1_checkpoint.load_checkpoint()
                if checkpoint and checkpoint.get('step') == 'text_analysis':
                    analysis_results = checkpoint.get('data', {}).get('analysis_results', analysis_results)
            else:
                logger.info("Step 1: Analyzing HTML structures with Analyzer Agent...")
                analysis_results = []
                for html_file in html_files:
                    file_identifier = html_file.get('url', html_file.get('path', 'unknown'))
                    result = self.analyzer.analyze_html_structure(
                        html_file['content'],
                        file_identifier
                    )
                    analysis_results.append(result)
                
                # Save step result to step1 flow directory
                step1_checkpoint.save_step_result("step1_text_analysis", analysis_results)
                step1_checkpoint.save_checkpoint("text_analysis", {
                    "analysis_results": analysis_results,
                    "file_identifiers": file_identifiers
                })
                logger.info(f"Step 1 results saved to flow{step1_flow_id}")
        
        # Step 2: Visual analysis (optional)
        if use_visual:
            # Check if we already have results from checkpoint
            if visual_results is not None:
                logger.info("Step 2: Using visual analysis results from checkpoint, skipping...")
                # Use existing flow directory from checkpoint
                step2_flow_id = completed_steps.get('step2', 2)
                step2_output_dir = Settings.get_flow_output_dir(step2_flow_id)
                step2_checkpoint = CheckpointManager(step2_output_dir)
            else:
                # Create new flow directory for this step
                step2_flow_id = Settings.get_next_flow_id()
                step2_output_dir = Settings.get_flow_output_dir(step2_flow_id)
                step2_checkpoint = CheckpointManager(step2_output_dir)
                
                # Check if step result exists, if yes, skip and load from file
                if step2_checkpoint.step_result_exists("step2_visual_analysis"):
                    logger.info("Step 2: Using cached visual analysis results (file exists)")
                    visual_results = step2_checkpoint.load_step_result("step2_visual_analysis")
                    # Also load from checkpoint if available
                    checkpoint = step2_checkpoint.load_checkpoint()
                    if checkpoint and checkpoint.get('step') == 'visual_analysis':
                        visual_results = checkpoint.get('data', {}).get('visual_results', visual_results)
                        analysis_results = checkpoint.get('data', {}).get('analysis_results', analysis_results)
                else:
                    logger.info("Step 2: Performing visual analysis...")
                    visual_results = []
                    for html_file in html_files:
                        file_identifier = html_file.get('url', html_file.get('path', 'unknown'))
                        visual_result = self.visual_analyzer.analyze_html_visually(
                            html_file['content'],
                            file_identifier
                        )
                        visual_results.append(visual_result)
                    
                    # Save step result to step2 flow directory
                    step2_checkpoint.save_step_result("step2_visual_analysis", visual_results)
                    step2_checkpoint.save_checkpoint("visual_analysis", {
                        "analysis_results": analysis_results,
                        "visual_results": visual_results,
                        "file_identifiers": file_identifiers
                    })
                    logger.info(f"Step 2 results saved to flow{step2_flow_id}")
        else:
            visual_results = []
        
        # Step 3: Orchestrator synthesizes results
        # Check if we already have results from checkpoint
        if synthesized is not None:
            logger.info("Step 3: Using synthesized results from checkpoint, skipping...")
            # Use existing flow directory from checkpoint
            step3_flow_id = completed_steps.get('step3', 3)
            step3_output_dir = Settings.get_flow_output_dir(step3_flow_id)
            step3_checkpoint = CheckpointManager(step3_output_dir)
        else:
            # Create new flow directory for this step
            step3_flow_id = Settings.get_next_flow_id()
            step3_output_dir = Settings.get_flow_output_dir(step3_flow_id)
            step3_checkpoint = CheckpointManager(step3_output_dir)
            
            # Check if step result exists, if yes, skip and load from file
            if step3_checkpoint.step_result_exists("step3_synthesized"):
                logger.info("Step 3: Using cached synthesized results (file exists)")
                synthesized = step3_checkpoint.load_step_result("step3_synthesized")
                # Also load from checkpoint if available
                checkpoint = step3_checkpoint.load_checkpoint()
                if checkpoint and checkpoint.get('step') == 'synthesized':
                    synthesized = checkpoint.get('data', {}).get('synthesized', synthesized)
                    analysis_results = checkpoint.get('data', {}).get('analysis_results', analysis_results)
                    visual_results = checkpoint.get('data', {}).get('visual_results', visual_results)
            else:
                logger.info("Step 3: Orchestrator synthesizing analysis results...")
                combined_results = {
                    "text_analysis": analysis_results,
                    "visual_analysis": visual_results if use_visual else []
                }
                
                synthesized = self.orchestrator.coordinate_analysis(file_identifiers, combined_results)
                
                # Save step result to step3 flow directory
                step3_checkpoint.save_step_result("step3_synthesized", synthesized)
                step3_checkpoint.save_checkpoint("synthesized", {
                    "analysis_results": analysis_results,
                    "visual_results": visual_results if use_visual else [],
                    "synthesized": synthesized,
                    "file_identifiers": file_identifiers
                })
                logger.info(f"Step 3 results saved to flow{step3_flow_id}")
        
        # Step 4: Generate final JSON schema
        # Check if we already have results from checkpoint
        if json_schema is not None:
            logger.info("Step 4: Using schema from checkpoint, skipping...")
            # Use existing flow directory from checkpoint
            step4_flow_id = completed_steps.get('step4', 4)
            step4_output_dir = Settings.get_flow_output_dir(step4_flow_id)
            step4_checkpoint = CheckpointManager(step4_output_dir)
            schema_path = step4_output_dir / 'extraction_schema.json'
        else:
            # Create new flow directory for this step
            step4_flow_id = Settings.get_next_flow_id()
            step4_output_dir = Settings.get_flow_output_dir(step4_flow_id)
            step4_checkpoint = CheckpointManager(step4_output_dir)
            
            # Check if step result exists, if yes, skip and load from file
            schema_path = step4_output_dir / 'extraction_schema.json'
            if step4_checkpoint.step_result_exists("step4_schema") or schema_path.exists():
                logger.info("Step 4: Using cached schema (file exists)")
                json_schema = step4_checkpoint.load_step_result("step4_schema")
                if json_schema is None and schema_path.exists():
                    with open(schema_path, 'r', encoding='utf-8') as f:
                        json_schema = json.load(f)
                # Also load from checkpoint if available
                checkpoint = step4_checkpoint.load_checkpoint()
                if checkpoint and checkpoint.get('step') == 'schema':
                    json_schema = checkpoint.get('data', {}).get('schema', json_schema)
                    synthesized = checkpoint.get('data', {}).get('synthesized', synthesized)
                    analysis_results = checkpoint.get('data', {}).get('analysis_results', analysis_results)
                    visual_results = checkpoint.get('data', {}).get('visual_results', visual_results)
            else:
                logger.info("Step 4: Generating final JSON schema...")
                json_schema = self.orchestrator.generate_final_schema(synthesized)
                
                # Save schema to step4 flow directory
                with open(schema_path, 'w', encoding='utf-8') as f:
                    json.dump(json_schema, f, indent=2, ensure_ascii=False)
                logger.info(f"Schema saved to {schema_path}")
                
                # Save step result to step4 flow directory
                step4_checkpoint.save_step_result("step4_schema", json_schema)
                step4_checkpoint.save_checkpoint("schema", {
                    "analysis_results": analysis_results,
                    "visual_results": visual_results if use_visual else [],
                    "synthesized": synthesized,
                    "schema": json_schema,
                    "file_identifiers": file_identifiers
                })
                logger.info(f"Step 4 results saved to flow{step4_flow_id}")
        
        # Step 5: Generate extraction code
        # Check if we already have code from checkpoint
        if extraction_code is not None:
            logger.info("Step 5: Using extraction code from checkpoint, skipping generation...")
            # Use existing flow directory from checkpoint
            step5_flow_id = completed_steps.get('step5', 5)
            step5_output_dir = Settings.get_flow_output_dir(step5_flow_id)
            step5_checkpoint = CheckpointManager(step5_output_dir)
            code_path = step5_output_dir / 'extraction_code.py'
            # Load code from file if exists
            if code_path.exists():
                with open(code_path, 'r', encoding='utf-8') as f:
                    extraction_code = f.read()
        else:
            # Check for existing incomplete flow5 directory first
            # Look for flow directories with step="schema" (indicating Step 5 failed)
            existing_flow5_id = None
            if Settings.OUTPUT_DIR.exists():
                for item in Settings.OUTPUT_DIR.iterdir():
                    if item.is_dir() and item.name.startswith('flow'):
                        try:
                            flow_num = int(item.name[4:])
                            # Check if this is a flow5 directory (or any flow with schema checkpoint but no code)
                            checkpoint_manager = CheckpointManager(item)
                            checkpoint = checkpoint_manager.load_checkpoint()
                            if checkpoint:
                                checkpoint_step = checkpoint.get('step')
                                # If checkpoint is "schema" and has code_generation_failed, reuse this flow
                                if checkpoint_step == "schema" and checkpoint.get('data', {}).get('code_generation_failed'):
                                    # This is an incomplete Step 5, reuse it
                                    existing_flow5_id = flow_num
                                    logger.info(f"Found incomplete Step 5 in {item.name}, will reuse it")
                                    break
                        except (ValueError, Exception):
                            continue
            
            if existing_flow5_id is not None:
                # Reuse existing incomplete flow5 directory
                step5_flow_id = existing_flow5_id
                step5_output_dir = Settings.get_flow_output_dir(step5_flow_id)
                step5_checkpoint = CheckpointManager(step5_output_dir)
                logger.info(f"Reusing flow{step5_flow_id} for Step 5 retry")
            else:
                # Create new flow directory for this step
                step5_flow_id = Settings.get_next_flow_id()
                step5_output_dir = Settings.get_flow_output_dir(step5_flow_id)
                step5_checkpoint = CheckpointManager(step5_output_dir)
                logger.info(f"Creating new flow{step5_flow_id} for Step 5")
            
            # Check if step result exists and was successfully completed
            code_path = step5_output_dir / 'extraction_code.py'
            
            # Check if code file exists AND checkpoint shows successful completion
            code_completed = False
            step5_checkpoint_data = step5_checkpoint.load_checkpoint()
            if step5_checkpoint_data:
                checkpoint_step = step5_checkpoint_data.get('step')
                # Only skip if checkpoint shows "code_generated" step was completed
                if checkpoint_step == "code_generated":
                    code_completed = True
                    extraction_code = step5_checkpoint_data.get('data', {}).get('code')
                    json_schema = step5_checkpoint_data.get('data', {}).get('schema', json_schema)
                    synthesized = step5_checkpoint_data.get('data', {}).get('synthesized', synthesized)
                    analysis_results = step5_checkpoint_data.get('data', {}).get('analysis_results', analysis_results)
                    visual_results = step5_checkpoint_data.get('data', {}).get('visual_results', visual_results)
            
            if code_path.exists() and code_completed:
                logger.info("Step 5: Using cached extraction code (file exists and was successfully completed)")
                if extraction_code is None:
                    with open(code_path, 'r', encoding='utf-8') as f:
                        extraction_code = f.read()
                # Check if it's fallback code (indicates previous failure)
                if "API generation failed" in extraction_code or "fallback template" in extraction_code:
                    logger.warning("Step 5: Found fallback code from previous failure, regenerating...")
                    code_completed = False  # Force regeneration
                    extraction_code = None
            
            if not code_completed:
                logger.info("Step 5: Generating extraction code...")
                try:
                    # Step 5: Generate code
                    extraction_code = self.code_generator.generate_extraction_code(json_schema)
                    
                    # Save code to step5 flow directory
                    with open(code_path, 'w', encoding='utf-8') as f:
                        f.write(extraction_code)
                    logger.info(f"Extraction code saved to {code_path}")
                    
                    # Save step result to step5 flow directory
                    step5_checkpoint.save_step_result("step5_code", extraction_code, "extraction_code.py")
                    
                    # Save checkpoint to step5 flow directory (step="code_generated", not "code" yet)
                    step5_checkpoint.save_checkpoint("code_generated", {
                        "analysis_results": analysis_results,
                        "visual_results": visual_results if use_visual else [],
                        "synthesized": synthesized,
                        "schema": json_schema,
                        "code": extraction_code,
                        "file_identifiers": file_identifiers
                    })
                    logger.info(f"Step 5 results saved to flow{step5_flow_id}")
                except Exception as e:
                    logger.error(f"Failed to generate extraction code: {e}")
                    # Remove incomplete code file if it exists (from fallback or partial write)
                    if code_path.exists():
                        try:
                            code_path.unlink()
                            logger.info("Removed incomplete extraction code file")
                        except Exception as cleanup_error:
                            logger.warning(f"Failed to remove incomplete code file: {cleanup_error}")
                    
                    # Save checkpoint with error, but step remains "schema" (not "code")
                    # This ensures next run will retry Step 5
                    step5_checkpoint.save_checkpoint("schema", {
                        "analysis_results": analysis_results,
                        "visual_results": visual_results if use_visual else [],
                        "synthesized": synthesized,
                        "schema": json_schema,
                        "file_identifiers": file_identifiers,
                        "error": f"Code generation failed: {str(e)}",
                        "code_generation_failed": True
                    })
                    raise  # Re-raise to allow caller to handle
        
        # Step 6: Validate and improve code (new flow directory)
        # Check if we already have validated code from checkpoint
        validated_code = None
        validation_result = None
        step6_flow_id = None
        step6_output_dir = None
        step6_checkpoint = None
        
        # Check for existing flow6 directory with validated code
        if Settings.OUTPUT_DIR.exists():
            for item in Settings.OUTPUT_DIR.iterdir():
                if item.is_dir() and item.name.startswith('flow'):
                    try:
                        flow_num = int(item.name[4:])
                        checkpoint_manager = CheckpointManager(item)
                        checkpoint = checkpoint_manager.load_checkpoint()
                        if checkpoint:
                            checkpoint_step = checkpoint.get('step')
                            # Look for flow6 with validated code
                            if checkpoint_step == "code_validated" or checkpoint_step == "code":
                                # This is Step 6 completed
                                step6_flow_id = flow_num
                                validated_code = checkpoint.get('data', {}).get('code')
                                validation_result = checkpoint.get('data', {}).get('validation')
                                logger.info(f"Found validated code in {item.name}")
                                break
                    except (ValueError, Exception):
                        continue
        
        if validated_code is not None and validation_result is not None:
            logger.info("Step 6: Using validated code from checkpoint, skipping validation...")
            extraction_code = validated_code
            step6_output_dir = Settings.get_flow_output_dir(step6_flow_id)
            step6_checkpoint = CheckpointManager(step6_output_dir)
            validated_code_path = step6_output_dir / 'extraction_code.py'
            
            # Step 6.5: Execute validated code on spread directory (even when resuming)
            logger.info("Step 6.5: Executing validated code on spread directory...")
            try:
                execution_results = self._execute_extraction_code(
                    validated_code_path, 
                    step6_output_dir,
                    json_schema
                )
                if execution_results:
                    logger.info(f"Step 6.5: Successfully executed code, processed {execution_results.get('processed_count', 0)} files")
                else:
                    logger.warning("Step 6.5: No files processed from spread directory")
            except Exception as e:
                logger.error(f"Step 6.5: Failed to execute code: {e}")
                import traceback
                logger.error(traceback.format_exc())
                # Don't fail the whole process, just log the error
        else:
            # Create new flow directory for Step 6
            step6_flow_id = Settings.get_next_flow_id()
            step6_output_dir = Settings.get_flow_output_dir(step6_flow_id)
            step6_checkpoint = CheckpointManager(step6_output_dir)
            
            logger.info("Step 6: Validating and improving code quality...")
            try:
                # Validate code (syntax + robustness)
                logger.info("Validating code syntax and robustness...")
                validation_result = self.code_validator.validate_code(extraction_code, json_schema)
                
                # Log validation results
                syntax_errors = validation_result.get("syntax_errors", [])
                robustness_issues = validation_result.get("robustness_issues", [])
                interface_issues = validation_result.get("interface_issues", [])
                warnings = validation_result.get("warnings", [])
                
                has_issues = len(syntax_errors) > 0 or len(robustness_issues) > 0 or len(interface_issues) > 0
                
                if has_issues:
                    logger.warning(f"Code validation found issues:")
                    if syntax_errors:
                        logger.warning(f"  - Syntax errors: {len(syntax_errors)}")
                        for err in syntax_errors[:3]:  # Show first 3
                            logger.warning(f"    * {err.get('type')}: {err.get('message')}")
                    if robustness_issues:
                        logger.warning(f"  - Robustness issues: {len(robustness_issues)}")
                        for issue in robustness_issues[:3]:  # Show first 3
                            logger.warning(f"    * {issue.get('type')} ({issue.get('severity', 'unknown')}): {issue.get('message')}")
                    if interface_issues:
                        logger.warning(f"  - Interface compliance issues: {len(interface_issues)}")
                        for issue in interface_issues[:3]:  # Show first 3
                            logger.warning(f"    * {issue.get('type')} ({issue.get('severity', 'unknown')}): {issue.get('message')}")
                    if warnings:
                        logger.info(f"  - Warnings: {len(warnings)}")
                        for warn in warnings[:3]:  # Show first 3
                            logger.info(f"    * {warn.get('type')}: {warn.get('message')}")
                    
                    # Try to fix code using AI
                    if validation_result.get("fixed_code"):
                        logger.info("Attempting to fix code based on validation results...")
                        extraction_code = self.code_validator.fix_code(extraction_code, validation_result)
                        logger.info("Code fixed based on validation results")
                        
                        # Re-validate fixed code to ensure issues are resolved
                        logger.info("Re-validating fixed code...")
                        revalidation_result = self.code_validator.validate_code(extraction_code, json_schema)
                        remaining_syntax = len(revalidation_result.get("syntax_errors", []))
                        remaining_robustness = len(revalidation_result.get("robustness_issues", []))
                        remaining_interface = len(revalidation_result.get("interface_issues", []))
                        
                        if remaining_syntax == 0 and remaining_robustness == 0 and remaining_interface == 0:
                            logger.info("✓ All issues fixed successfully")
                        else:
                            logger.warning(f"Some issues remain: {remaining_syntax} syntax errors, {remaining_robustness} robustness issues, {remaining_interface} interface issues")
                            # Update validation result with revalidation
                            validation_result = revalidation_result
                    else:
                        logger.warning("Could not automatically fix code, using original")
                else:
                    if warnings:
                        logger.info(f"Code validation passed with {len(warnings)} warnings (non-critical)")
                    else:
                        logger.info("Code validation passed: no critical issues found")
                
                # Add validation marker to code (even if no fixes were needed)
                # This distinguishes flow6 code from flow5 code
                if not validation_result.get("fixed_code"):
                    # Add a comment at the top indicating this is validated code
                    validation_marker = "# This code has been validated and verified\n"
                    # Check if code already has a header comment
                    if extraction_code.startswith("#"):
                        # Find the end of the first comment block
                        lines = extraction_code.split('\n')
                        insert_pos = 0
                        for i, line in enumerate(lines):
                            if line.strip().startswith("#"):
                                insert_pos = i + 1
                            else:
                                break
                        # Insert validation marker after header comments
                        lines.insert(insert_pos, validation_marker)
                        extraction_code = '\n'.join(lines)
                    else:
                        # Add at the very beginning
                        extraction_code = validation_marker + extraction_code
                    logger.info("Added validation marker to code")
                
                # Save validation results to step6 flow directory
                validation_path = step6_output_dir / 'code_validation_result.json'
                with open(validation_path, 'w', encoding='utf-8') as f:
                    json.dump(validation_result, f, indent=2, ensure_ascii=False)
                logger.info(f"Validation results saved to {validation_path}")
                
                # Save validated/fixed code to step6 flow directory
                validated_code_path = step6_output_dir / 'extraction_code.py'
                with open(validated_code_path, 'w', encoding='utf-8') as f:
                    f.write(extraction_code)
                logger.info(f"Validated extraction code saved to {validated_code_path}")
                
                # Save checkpoint to step6 flow directory
                step6_checkpoint.save_checkpoint("code_validated", {
                    "analysis_results": analysis_results,
                    "visual_results": visual_results if use_visual else [],
                    "synthesized": synthesized,
                    "schema": json_schema,
                    "code": extraction_code,
                    "validation": validation_result,
                    "file_identifiers": file_identifiers
                })
                logger.info(f"Step 6 results saved to flow{step6_flow_id}")
                
                # Step 6.5: Execute validated code on spread directory
                logger.info("Step 6.5: Executing validated code on spread directory...")
                try:
                    execution_results = self._execute_extraction_code(
                        validated_code_path, 
                        step6_output_dir,
                        json_schema
                    )
                    if execution_results:
                        logger.info(f"Step 6.5: Successfully executed code, processed {execution_results.get('processed_count', 0)} files")
                    else:
                        logger.warning("Step 6.5: No files processed from spread directory")
                except Exception as e:
                    logger.error(f"Step 6.5: Failed to execute code: {e}")
                    # Don't fail the whole process, just log the error
                    
            except Exception as e:
                logger.error(f"Step 6 failed: {e}")
                import traceback
                logger.error(traceback.format_exc())
                # Save error checkpoint
                step6_checkpoint.save_checkpoint("code_generated", {
                    "analysis_results": analysis_results,
                    "visual_results": visual_results if use_visual else [],
                    "synthesized": synthesized,
                    "schema": json_schema,
                    "code": extraction_code,
                    "file_identifiers": file_identifiers,
                    "error": f"Code validation failed: {str(e)}",
                    "validation_failed": True
                })
                raise
        
        # Save intermediate results to each step's flow directory
        # Step 1 intermediate results
        step1_intermediate_path = step1_output_dir / 'intermediate_results.json'
        with open(step1_intermediate_path, 'w', encoding='utf-8') as f:
            json.dump({
                "html_files": file_identifiers,
                "analysis_results": analysis_results,
                "step": "step1_text_analysis",
                "flow_id": step1_flow_id
            }, f, indent=2, ensure_ascii=False)
        logger.info(f"Step 1 intermediate results saved to {step1_intermediate_path}")
        
        # Step 2 intermediate results (if visual analysis enabled)
        step2_intermediate_path = None
        if use_visual and visual_results:
            step2_intermediate_path = step2_output_dir / 'intermediate_results.json'
            with open(step2_intermediate_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "html_files": file_identifiers,
                    "analysis_results": analysis_results,
                    "visual_results": visual_results,
                    "step": "step2_visual_analysis",
                    "flow_id": step2_flow_id
                }, f, indent=2, ensure_ascii=False)
            logger.info(f"Step 2 intermediate results saved to {step2_intermediate_path}")
        
        # Step 3 intermediate results
        step3_intermediate_path = step3_output_dir / 'intermediate_results.json'
        with open(step3_intermediate_path, 'w', encoding='utf-8') as f:
            json.dump({
                "html_files": file_identifiers,
                "analysis_results": analysis_results,
                "visual_results": visual_results if use_visual else [],
                "synthesized": synthesized,
                "step": "step3_synthesized",
                "flow_id": step3_flow_id
            }, f, indent=2, ensure_ascii=False)
        logger.info(f"Step 3 intermediate results saved to {step3_intermediate_path}")
        
        # Step 4 intermediate results
        step4_intermediate_path = step4_output_dir / 'intermediate_results.json'
        with open(step4_intermediate_path, 'w', encoding='utf-8') as f:
            json.dump({
                "html_files": file_identifiers,
                "analysis_results": analysis_results,
                "visual_results": visual_results if use_visual else [],
                "synthesized": synthesized,
                "schema": json_schema,
                "step": "step4_schema",
                "flow_id": step4_flow_id
            }, f, indent=2, ensure_ascii=False)
        logger.info(f"Step 4 intermediate results saved to {step4_intermediate_path}")
        
        # Step 5 intermediate results
        step5_intermediate_path = step5_output_dir / 'intermediate_results.json'
        with open(step5_intermediate_path, 'w', encoding='utf-8') as f:
            json.dump({
                "html_files": file_identifiers,
                "analysis_results": analysis_results,
                "visual_results": visual_results if use_visual else [],
                "synthesized": synthesized,
                "schema": json_schema,
                "code": extraction_code,
                "step": "step5_code_generated",
                "flow_id": step5_flow_id
            }, f, indent=2, ensure_ascii=False)
        logger.info(f"Step 5 intermediate results saved to {step5_intermediate_path}")
        
        # Step 6 intermediate results (final comprehensive results)
        step6_intermediate_path = step6_output_dir / 'intermediate_results.json'
        with open(step6_intermediate_path, 'w', encoding='utf-8') as f:
            json.dump({
                "html_files": file_identifiers,
                "analysis_results": analysis_results,
                "visual_results": visual_results if use_visual else [],
                "synthesized": synthesized,
                "schema": json_schema,
                "code": extraction_code,
                "validation": validation_result,
                "step": "step6_code_validated",
                "flow_directories": {
                    "step1": f"flow{step1_flow_id}",
                    "step2": f"flow{step2_flow_id}" if use_visual else None,
                    "step3": f"flow{step3_flow_id}",
                    "step4": f"flow{step4_flow_id}",
                    "step5": f"flow{step5_flow_id}",
                    "step6": f"flow{step6_flow_id}"
                }
            }, f, indent=2, ensure_ascii=False)
        logger.info(f"Step 6 intermediate results saved to {step6_intermediate_path}")
        
        # Step 7: Convert JSON results to Markdown format
        # Check if we already have markdown conversion results from checkpoint
        markdown_converter_code = None
        content_analysis = None
        step7_flow_id = None
        step7_output_dir = None
        step7_checkpoint = None
        
        # Check for existing flow7 directory with markdown conversion
        if Settings.OUTPUT_DIR.exists():
            for item in Settings.OUTPUT_DIR.iterdir():
                if item.is_dir() and item.name.startswith('flow'):
                    try:
                        flow_num = int(item.name[4:])
                        checkpoint_manager = CheckpointManager(item)
                        checkpoint = checkpoint_manager.load_checkpoint()
                        if checkpoint:
                            checkpoint_step = checkpoint.get('step')
                            # Look for flow7 with markdown conversion
                            if checkpoint_step == "markdown_converted":
                                step7_flow_id = flow_num
                                markdown_converter_code = checkpoint.get('data', {}).get('markdown_converter_code')
                                content_analysis = checkpoint.get('data', {}).get('content_analysis')
                                logger.info(f"Found markdown conversion in {item.name}")
                                break
                    except (ValueError, Exception):
                        continue
        
        if markdown_converter_code is not None and content_analysis is not None:
            logger.info("Step 7: Using markdown converter code from checkpoint, skipping generation...")
            step7_output_dir = Settings.get_flow_output_dir(step7_flow_id)
            step7_checkpoint = CheckpointManager(step7_output_dir)
            converter_code_path = step7_output_dir / 'markdown_converter.py'
            
            # Step 7.5: Execute markdown conversion (even when resuming)
            logger.info("Step 7.5: Executing markdown conversion on JSON results...")
            try:
                conversion_results = self._execute_markdown_conversion(
                    converter_code_path,
                    step6_output_dir / 'extraction_results',
                    step7_output_dir
                )
                if conversion_results:
                    logger.info(f"Step 7.5: Successfully converted {conversion_results.get('processed_count', 0)} files to Markdown")
                else:
                    logger.warning("Step 7.5: No files converted to Markdown")
            except Exception as e:
                logger.error(f"Step 7.5: Failed to execute markdown conversion: {e}")
                import traceback
                logger.error(traceback.format_exc())
        else:
            # Create new flow directory for Step 7
            step7_flow_id = Settings.get_next_flow_id()
            step7_output_dir = Settings.get_flow_output_dir(step7_flow_id)
            step7_checkpoint = CheckpointManager(step7_output_dir)
            
            logger.info("Step 7: Analyzing JSON results and generating Markdown converter code...")
            try:
                # Step 7.1: Load JSON results from flow6/extraction_results
                extraction_results_dir = step6_output_dir / 'extraction_results'
                if not extraction_results_dir.exists():
                    logger.warning(f"Extraction results directory not found: {extraction_results_dir}")
                    logger.info("Step 7 skipped: No extraction results to convert")
                else:
                    # Load all JSON files
                    json_files = list(extraction_results_dir.glob('*.json'))
                    if not json_files:
                        logger.warning("No JSON files found in extraction_results directory")
                        logger.info("Step 7 skipped: No JSON files to convert")
                    else:
                        logger.info(f"Found {len(json_files)} JSON files to analyze")
                        
                        # Load sample JSON files for analysis
                        json_results = []
                        for json_file in json_files[:5]:  # Sample first 5 files
                            try:
                                with open(json_file, 'r', encoding='utf-8') as f:
                                    json_results.append(json.load(f))
                            except Exception as e:
                                logger.warning(f"Failed to load {json_file}: {e}")
                        
                        if not json_results:
                            logger.warning("Failed to load any JSON results for analysis")
                        else:
                            # Step 7.2: Analyze content fields
                            logger.info("Step 7.2: Analyzing content fields in JSON results...")
                            content_analysis = self.markdown_converter.analyze_content_fields(json_results)
                            
                            if 'error' in content_analysis:
                                logger.error(f"Failed to analyze content fields: {content_analysis.get('error')}")
                                raise ValueError(f"Content analysis failed: {content_analysis.get('error')}")
                            
                            logger.info(f"Content analysis completed. Main content fields: {content_analysis.get('main_content_fields', [])}")
                            
                            # Step 7.3: Generate markdown converter code
                            logger.info("Step 7.3: Generating Markdown converter code...")
                            sample_json = json_results[0] if json_results else {}
                            markdown_converter_code = self.markdown_converter.generate_markdown_converter_code(
                                content_analysis,
                                sample_json
                            )
                            
                            # Step 7.3.5: Validate generated code syntax
                            logger.info("Step 7.3.5: Validating generated code syntax...")
                            max_retries = 2
                            retry_count = 0
                            
                            while retry_count <= max_retries:
                                try:
                                    compile(markdown_converter_code, '<string>', 'exec')
                                    logger.info("Generated code syntax is valid")
                                    break  # Success, exit loop
                                except SyntaxError as e:
                                    if retry_count == 0:
                                        logger.error(f"Generated code has syntax errors: {e}")
                                        logger.info("Attempting to fix syntax errors...")
                                        # Try to fix common syntax errors
                                        markdown_converter_code = self._fix_markdown_converter_syntax(markdown_converter_code, e)
                                        retry_count += 1
                                    elif retry_count == 1:
                                        logger.error(f"Failed to fix syntax errors: {e}")
                                        logger.warning("Regenerating markdown converter code with stricter requirements...")
                                        # Regenerate with more explicit instructions
                                        markdown_converter_code = self.markdown_converter.generate_markdown_converter_code(
                                            content_analysis,
                                            sample_json,
                                            retry=True  # Signal that this is a retry
                                        )
                                        retry_count += 1
                                    else:
                                        logger.error(f"Failed to generate valid code after {max_retries} attempts: {e}")
                                        raise ValueError(f"Generated code has unfixable syntax errors after {max_retries} attempts: {e}")
                            
                            # Save converter code to step7 flow directory
                            converter_code_path = step7_output_dir / 'markdown_converter.py'
                            with open(converter_code_path, 'w', encoding='utf-8') as f:
                                f.write(markdown_converter_code)
                            logger.info(f"Markdown converter code saved to {converter_code_path}")
                            
                            # Save checkpoint
                            step7_checkpoint.save_checkpoint("markdown_converted", {
                                "content_analysis": content_analysis,
                                "markdown_converter_code": markdown_converter_code,
                                "json_files_count": len(json_files),
                                "file_identifiers": file_identifiers
                            })
                            logger.info(f"Step 7 results saved to flow{step7_flow_id}")
                            
                            # Step 7.5: Execute markdown conversion
                            logger.info("Step 7.5: Executing markdown conversion on JSON results...")
                            try:
                                conversion_results = self._execute_markdown_conversion(
                                    converter_code_path,
                                    extraction_results_dir,
                                    step7_output_dir
                                )
                                if conversion_results:
                                    logger.info(f"Step 7.5: Successfully converted {conversion_results.get('processed_count', 0)} files to Markdown")
                                else:
                                    logger.warning("Step 7.5: No files converted to Markdown")
                            except Exception as e:
                                logger.error(f"Step 7.5: Failed to execute markdown conversion: {e}")
                                import traceback
                                logger.error(traceback.format_exc())
                                # Don't fail the whole process, just log the error
                
            except Exception as e:
                logger.error(f"Step 7 failed: {e}")
                import traceback
                logger.error(traceback.format_exc())
                # Save error checkpoint
                step7_checkpoint.save_checkpoint("code_validated", {
                    "error": f"Markdown conversion failed: {str(e)}",
                    "markdown_conversion_failed": True
                })
                # Don't raise - markdown conversion is optional
        
        # Step 7 intermediate results
        if step7_output_dir:
            step7_intermediate_path = step7_output_dir / 'intermediate_results.json'
            with open(step7_intermediate_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "content_analysis": content_analysis,
                    "markdown_converter_code": markdown_converter_code,
                    "step": "step7_markdown_converted",
                    "flow_id": step7_flow_id
                }, f, indent=2, ensure_ascii=False)
            logger.info(f"Step 7 intermediate results saved to {step7_intermediate_path}")
        
        # Final code path is from step6 (validated code)
        final_code_path = step6_output_dir / 'extraction_code.py'
        
        return {
            "success": True,
            "schema_path": str(schema_path),
            "code_path": str(final_code_path),
            "intermediate_paths": {
                "step1": str(step1_intermediate_path),
                "step2": str(step2_intermediate_path) if use_visual and visual_results else None,
                "step3": str(step3_intermediate_path),
                "step4": str(step4_intermediate_path),
                "step5": str(step5_intermediate_path),
                "step6": str(step6_intermediate_path),
                "step7": str(step7_intermediate_path) if step7_output_dir else None
            },
            "schema": json_schema,
            "code": extraction_code,
            "flow_directories": {
                "step1": f"flow{step1_flow_id}",
                "step2": f"flow{step2_flow_id}" if use_visual else None,
                "step3": f"flow{step3_flow_id}",
                "step4": f"flow{step4_flow_id}",
                "step5": f"flow{step5_flow_id}",
                "step6": f"flow{step6_flow_id}",
                "step7": f"flow{step7_flow_id}" if step7_output_dir else None
            }
        }


def main():
    """
    Main entry point
    """
    parser = argparse.ArgumentParser(
        description='HTML Agent Analysis System - Analyze HTML files and generate extraction code'
    )
    parser.add_argument(
        'input',
        type=str,
        nargs='?',
        default=None,
        help='Input path: directory containing HTML files OR URL list file (e.g., urls.txt). '
             'If not specified, will use typical directory from config (data/input/typcial/)'
    )
    parser.add_argument(
        '--no-visual',
        action='store_true',
        help='Disable visual analysis (faster but less accurate)'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default=None,
        help='Output directory for results (default: data/output/flow{N}/)'
    )
    parser.add_argument(
        '--flow-id',
        type=int,
        default=None,
        help='Flow ID for output directory. If not specified, will auto-increment to next available flow number'
    )
    parser.add_argument(
        '--auto-flow',
        action='store_true',
        default=True,
        help='Automatically use next available flow ID (default: True). Use --no-auto-flow to disable'
    )
    parser.add_argument(
        '--no-auto-flow',
        action='store_false',
        dest='auto_flow',
        help='Disable auto-increment flow ID, use flow-id or default to flow1'
    )
    parser.add_argument(
        '--input-type',
        type=str,
        choices=['typical', 'custom'],
        default='typical',
        help='Input type: typical (learning content for agent), or custom (use --input path). Note: spread directory is for generated code execution, not for agent input.'
    )
    parser.add_argument(
        '--resume',
        action='store_true',
        default=True,
        help='Resume from last checkpoint if available (default: True). Use --no-resume to disable'
    )
    parser.add_argument(
        '--no-resume',
        action='store_false',
        dest='resume',
        help='Force restart, ignore checkpoints'
    )
    
    args = parser.parse_args()
    
    # Initialize directories
    Settings.initialize_directories()
    
    # Determine input path and handle preprocessing (download HTML if needed)
    # Note: spread directory is for generated code execution, not for agent input
    # Agent only processes typical directory (learning content)
    if args.input:
        # Use custom input path
        input_path = Path(args.input)
    elif args.input_type == 'typical':
        # Use typical directory (learning content for agent)
        # Preprocessing: Check if HTML files exist, if not, download from urls.txt
        if Settings.TYPICAL_HTML_DIR.exists() and any(Settings.TYPICAL_HTML_DIR.iterdir()):
            # HTML files already exist, use them
            input_path = Settings.TYPICAL_HTML_DIR
            logger.info(f"Using existing typical HTML directory: {input_path}")
        elif Settings.TYPICAL_URLS_FILE.exists():
            # No HTML files, but urls.txt exists - download HTML files
            logger.info("No HTML files found in typical/html, downloading from urls.txt...")
            urls = URLDownloader.load_urls_from_file(str(Settings.TYPICAL_URLS_FILE))
            if not urls:
                logger.error("No valid URLs found in typical/urls.txt")
                return 1
            
            # Download to typical/html directory
            Settings.TYPICAL_HTML_DIR.mkdir(parents=True, exist_ok=True)
            html_files = URLDownloader.download_multiple_urls(urls, output_dir=str(Settings.TYPICAL_HTML_DIR))
            
            if not html_files:
                logger.error("Failed to download HTML files")
                return 1
            
            logger.info(f"Successfully downloaded {len(html_files)} HTML files to {Settings.TYPICAL_HTML_DIR}")
            input_path = Settings.TYPICAL_HTML_DIR
        else:
            logger.error(f"Typical directory has no HTML files or urls.txt. Check: {Settings.TYPICAL_DIR}")
            return 1
    else:
        # Custom input type requires explicit input path
        logger.error("No input specified and input-type is 'custom'. Please provide --input path.")
        return 1
    
    # Validate input path
    if not input_path.exists():
        logger.error(f"Input path does not exist: {input_path}")
        return 1
    
    # Note: Each step will create its own flow directory automatically
    # We don't need to set a specific output_dir here anymore
    # If user wants custom output base directory, we can set it
    if args.output_dir:
        # Use custom output base directory (each step will still create its own flow subdirectory)
        custom_output_base = Path(args.output_dir).resolve()
        logger.info(f"Using custom output base directory: {custom_output_base}")
        # Temporarily override OUTPUT_DIR base
        original_output_dir = Settings.OUTPUT_DIR
        Settings.OUTPUT_DIR = custom_output_base
    else:
        # Use default output directory from settings
        # Each step will create flow{N} subdirectories under this
        logger.info(f"Using default output base directory: {Settings.OUTPUT_DIR}")
        original_output_dir = None  # No override needed
    
    try:
        # Initialize and run system
        # Each step will automatically create its own flow directory
        system = HTMLAgentSystem()
        # resume defaults to True, can be disabled with --no-resume
        result = system.process_input(str(input_path), use_visual=not args.no_visual, resume=args.resume)
    finally:
        # Restore original OUTPUT_DIR if it was overridden
        if original_output_dir is not None:
            Settings.OUTPUT_DIR = original_output_dir
    
    if result.get('success'):
        logger.info("")
        logger.info("=" * 60)
        logger.info("✓ Analysis completed successfully!")
        logger.info(f"  Schema: {result['schema_path']}")
        logger.info(f"  Code: {result['code_path']}")
        logger.info("=" * 60)
        return 0
    else:
        logger.error("")
        logger.error("✗ Analysis failed")
        return 1


if __name__ == '__main__':
    exit(main())

