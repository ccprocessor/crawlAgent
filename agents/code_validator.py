"""
Code Validator Agent - Validates generated code for syntax errors and robustness
"""
import ast
import logging
import re
from typing import Dict, Any, List, Optional, Tuple
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


class CodeValidatorAgent:
    """
    Code validator agent that checks generated code for syntax errors,
    robustness issues, and provides improvement suggestions
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
        
        if use_anthropic and ANTHROPIC_AVAILABLE:
            self.client_type = 'anthropic'
            self.client = Anthropic(
                api_key=Settings.ANTHROPIC_API_KEY,
                base_url=Settings.ANTHROPIC_BASE_URL
            )
            self.model = Settings.ANTHROPIC_MODEL
            logger.info(f"Using Anthropic API for code validation: {Settings.ANTHROPIC_BASE_URL}")
        elif OPENAI_AVAILABLE:
            self.client_type = 'openai'
            self.client = OpenAI(
                api_key=Settings.OPENAI_API_KEY,
                base_url=Settings.OPENAI_BASE_URL
            )
            self.model = Settings.OPENAI_MODEL
            logger.info(f"Using OpenAI API for code validation: {Settings.OPENAI_BASE_URL}")
        else:
            raise ImportError("Neither Anthropic nor OpenAI packages are available")
    
    def validate_code(self, code: str, json_schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Validate code for syntax errors and robustness issues
        
        Args:
            code: Python code to validate
            json_schema: Optional JSON schema for context
            
        Returns:
            Dictionary with validation results
        """
        result = {
            "valid": True,
            "syntax_errors": [],
            "robustness_issues": [],
            "interface_issues": [],  # New: interface compliance issues
            "suggestions": [],
            "fixed_code": None,
            "warnings": []
        }
        
        # Step 1: Syntax validation
        syntax_result = self._check_syntax(code)
        result["syntax_errors"] = syntax_result["errors"]
        result["warnings"].extend(syntax_result["warnings"])
        
        if syntax_result["errors"]:
            result["valid"] = False
            logger.error(f"Syntax errors found: {len(syntax_result['errors'])}")
        
        # Step 2: Static analysis for robustness
        robustness_result = self._check_robustness(code)
        result["robustness_issues"] = robustness_result["issues"]
        result["warnings"].extend(robustness_result["warnings"])
        
        if robustness_result["issues"]:
            logger.warning(f"Robustness issues found: {len(robustness_result['issues'])}")
            result["valid"] = False  # Mark as invalid if robustness issues found
        
        # Step 3: Interface compliance check (input/output validation)
        interface_result = self._check_interface_compliance(code)
        result["interface_issues"] = interface_result["issues"]
        result["warnings"].extend(interface_result["warnings"])
        
        if interface_result["issues"]:
            logger.warning(f"Interface compliance issues found: {len(interface_result['issues'])}")
            result["valid"] = False  # Mark as invalid if interface issues found
        
        # Step 4: AI-powered code review
        # Always review if there are syntax errors, robustness issues, interface issues, or warnings
        if result["syntax_errors"] or result["robustness_issues"] or result.get("interface_issues", []) or robustness_result["warnings"]:
            logger.info("Running AI code review to fix issues and improve robustness...")
            ai_review = self._ai_code_review(code, result, json_schema)
            result["suggestions"] = ai_review.get("suggestions", [])
            result["fixed_code"] = ai_review.get("fixed_code")
            if result["fixed_code"]:
                logger.info("AI provided fixed code")
            else:
                logger.warning("AI review did not provide fixed code")
        
        return result
    
    def _check_syntax(self, code: str) -> Dict[str, Any]:
        """
        Check Python syntax using AST parser
        """
        errors = []
        warnings = []
        
        try:
            # Try to parse the code
            ast.parse(code)
        except SyntaxError as e:
            errors.append({
                "type": "SyntaxError",
                "message": str(e),
                "line": e.lineno,
                "offset": e.offset,
                "text": e.text
            })
        except Exception as e:
            errors.append({
                "type": "ParseError",
                "message": f"Failed to parse code: {str(e)}"
            })
        
        # Check for common Python issues
        # Check for invalid escape sequences
        lines = code.split('\n')
        for i, line in enumerate(lines, 1):
            # Check for invalid escape sequences (not in raw strings or comments)
            if not line.strip().startswith('#') and not line.strip().startswith('"""') and not line.strip().startswith("'''"):
                if re.search(r'[^r]"[^"]*\\[^\\"nrtbf]', line) or re.search(r"[^r]'[^']*\\[^\\'nrtbf]", line):
                    warnings.append({
                        "type": "InvalidEscapeSequence",
                        "message": f"Possible invalid escape sequence in line {i}",
                        "line": i,
                        "suggestion": "Use raw string (r\"...\") or escape backslashes"
                    })
        
        # Check for JSON boolean values in Python code
        if re.search(r':\s*(true|false)\s*[,}]', code):
            warnings.append({
                "type": "JSONBooleanInPython",
                "message": "Found JSON boolean values (true/false) in Python code",
                "suggestion": "Replace with Python boolean values (True/False)"
            })
        
        return {"errors": errors, "warnings": warnings}
    
    def _check_robustness(self, code: str) -> Dict[str, Any]:
        """
        Check code robustness using static analysis
        """
        issues = []
        warnings = []
        
        # Check for error handling in extraction functions
        extraction_functions = ['def extract', 'def extract_content', 'def extract_batch']
        has_extraction_func = any(func in code for func in extraction_functions)
        if has_extraction_func:
            # Check if main extraction functions have error handling
            if 'try' not in code or 'except' not in code:
                issues.append({
                    "type": "MissingErrorHandling",
                    "severity": "high",
                    "message": "Extraction functions lack error handling",
                    "suggestion": "Add try-except blocks to handle parsing errors, file I/O errors, and XPath failures"
                })
        
        # Check for None checks after XPath operations
        xpath_patterns = [
            r'\.xpath\s*\(',
            r'etree\.XPath\s*\(',
            r'findall\s*\(',
            r'find\s*\('
        ]
        has_xpath = any(re.search(pattern, code) for pattern in xpath_patterns)
        if has_xpath:
            # Check if code handles None results from XPath
            xpath_usage_count = sum(len(re.findall(pattern, code)) for pattern in xpath_patterns)
            none_check_count = len(re.findall(r'\bif\s+.*\s+is\s+not\s+None\b|\bif\s+.*\s+is\s+None\b|\bif\s+.*\s+!=\s+None\b|\bif\s+.*\s+==\s+None\b', code))
            if xpath_usage_count > none_check_count:
                issues.append({
                    "type": "MissingNoneCheck",
                    "severity": "medium",
                    "message": f"XPath operations ({xpath_usage_count}) may return None, but only {none_check_count} None checks found",
                    "suggestion": "Add None checks after XPath operations to prevent AttributeError"
                })
        
        # Check for empty list handling
        if has_xpath:
            list_operations = ['xpath', 'findall']
            has_list_ops = any(op in code for op in list_operations)
            if has_list_ops:
                # Check if code checks for empty lists
                empty_checks = len(re.findall(r'len\s*\(\s*\w+\s*\)\s*==\s*0|len\s*\(\s*\w+\s*\)\s*>\s*0|\w+\s+if\s+\w+\s+else', code))
                if empty_checks < 2:  # Should have at least some empty checks
                    warnings.append({
                        "type": "MissingEmptyCheck",
                        "severity": "medium",
                        "message": "XPath may return empty lists, consider checking length before processing",
                        "suggestion": "Add checks like 'if elements:' or 'if len(elements) > 0:' before processing XPath results"
                    })
        
        # Check for proper error handling in file operations
        file_operations = ['open(', 'read_file', 'Path(']
        has_file_ops = any(op in code for op in file_operations)
        if has_file_ops:
            file_error_handling = len(re.findall(r'FileNotFoundError|IOError|OSError|except.*:', code))
            if file_error_handling == 0:
                issues.append({
                    "type": "MissingFileErrorHandling",
                    "severity": "high",
                    "message": "File operations lack error handling",
                    "suggestion": "Add try-except blocks to handle FileNotFoundError, PermissionError, and other I/O errors"
                })
        
        # Check for proper imports
        required_imports = {
            'lxml': ['lxml', 'etree'],
            'json': ['json'],
            'logging': ['logging', 'logger']
        }
        missing_imports = []
        for module, keywords in required_imports.items():
            # Check if module is used but not imported
            module_used = any(keyword in code for keyword in keywords)
            if module_used:
                # Check if imported
                if f'import {module}' not in code and f'from {module}' not in code:
                    missing_imports.append(module)
        
        if missing_imports:
            issues.append({
                "type": "MissingImports",
                "severity": "high",
                "message": f"Missing required imports: {', '.join(missing_imports)}",
                "suggestion": f"Add imports: {', '.join(f'import {m}' for m in missing_imports)}"
            })
        
        # Check for hardcoded paths
        if re.search(r'[CD]:\\[^"]*', code) or re.search(r'/.*/[^"]*\.html', code):
            issues.append({
                "type": "HardcodedPath",
                "severity": "medium",
                "message": "Found hardcoded file paths",
                "suggestion": "Use pathlib.Path or os.path.join() for cross-platform compatibility"
            })
        
        # Check for proper return value handling
        if 'def extract' in code:
            # Check if function handles edge cases in return values
            return_statements = len(re.findall(r'return\s+', code))
            if return_statements < 2:
                warnings.append({
                    "type": "LimitedReturnPaths",
                    "severity": "low",
                    "message": "Extraction function may not handle all edge cases",
                    "suggestion": "Ensure function returns appropriate values for empty results, errors, and success cases"
                })
        
        # Check for defensive programming - validate inputs
        if 'def extract' in code or 'def extract_content' in code:
            # Check if function validates input parameters
            input_validation = len(re.findall(r'if\s+.*\s+is\s+None|if\s+not\s+.*|assert\s+', code))
            if input_validation == 0:
                warnings.append({
                    "type": "MissingInputValidation",
                    "severity": "medium",
                    "message": "Function may not validate input parameters",
                    "suggestion": "Add input validation to check for None, empty strings, or invalid file paths"
                })
        
        return {"issues": issues, "warnings": warnings}
    
    def _check_interface_compliance(self, code: str) -> Dict[str, Any]:
        """
        Strictly check interface compliance:
        - Input parameter validation (function signatures)
        - Output format validation (return types)
        - Required class/function structure
        """
        issues = []
        warnings = []
        
        try:
            # Parse code to AST for detailed analysis
            tree = ast.parse(code)
            
            # Check for HTMLExtractor class
            html_extractor_class = None
            extract_method = None
            extract_content_func = None
            
            for node in ast.walk(tree):
                # Find HTMLExtractor class
                if isinstance(node, ast.ClassDef) and node.name == 'HTMLExtractor':
                    html_extractor_class = node
                    
                    # Check __init__ method
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                            init_params = [arg.arg for arg in item.args.args if arg.arg != 'self']
                            
                            # Must have 'schema' parameter
                            if 'schema' not in init_params:
                                issues.append({
                                    "type": "MissingSchemaParameter",
                                    "severity": "high",
                                    "message": "HTMLExtractor.__init__() must accept 'schema' parameter",
                                    "suggestion": "Add 'schema: Dict[str, Any]' parameter to __init__ method"
                                })
                            
                            # Check type hints
                            if item.args.args:
                                schema_arg = None
                                for i, arg in enumerate(item.args.args):
                                    if arg.arg == 'schema':
                                        schema_arg = arg
                                        break
                                
                                if schema_arg and item.returns is None:
                                    # Check if annotation exists
                                    if not hasattr(schema_arg, 'annotation') or schema_arg.annotation is None:
                                        warnings.append({
                                            "type": "MissingTypeHint",
                                            "severity": "medium",
                                            "message": "HTMLExtractor.__init__ schema parameter should have type hint",
                                            "suggestion": "Add type hint: schema: Dict[str, Any]"
                                        })
                    
                    # Check extract method
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and item.name == 'extract':
                            extract_method = item
                            
                            # Check parameters - must accept html_content or file_path
                            params = [arg.arg for arg in item.args.args if arg.arg != 'self']
                            has_html_content = 'html_content' in params
                            has_file_path = 'file_path' in params
                            
                            if not has_html_content and not has_file_path:
                                issues.append({
                                    "type": "InvalidExtractParameters",
                                    "severity": "high",
                                    "message": "extract() method must accept 'html_content' or 'file_path' parameter",
                                    "suggestion": "Add parameter: html_content: Optional[str] = None, file_path: Optional[str] = None"
                                })
                            
                            # Check return type annotation
                            if item.returns is None:
                                issues.append({
                                    "type": "MissingReturnType",
                                    "severity": "high",
                                    "message": "extract() method must have return type annotation",
                                    "suggestion": "Add return type: -> Dict[str, Any]"
                                })
                            else:
                                # Verify return type is Dict
                                return_type_str = ast.unparse(item.returns) if hasattr(ast, 'unparse') else str(item.returns)
                                if 'Dict' not in return_type_str and 'dict' not in return_type_str.lower():
                                    issues.append({
                                        "type": "InvalidReturnType",
                                        "severity": "high",
                                        "message": f"extract() method must return Dict[str, Any], found: {return_type_str}",
                                        "suggestion": "Change return type annotation to: -> Dict[str, Any]"
                                    })
            
            # Check for forbidden method/function names
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    func_name = node.name
                    # Check if it's a standalone function (not in HTMLExtractor class)
                    is_standalone = True
                    for parent in ast.walk(tree):
                        if isinstance(parent, ast.ClassDef) and parent.name == 'HTMLExtractor':
                            if node in parent.body:
                                is_standalone = False
                                break
                    
                    # Forbidden standalone functions
                    if is_standalone and func_name == 'extract_content':
                        issues.append({
                            "type": "ForbiddenFunction",
                            "severity": "high",
                            "message": "Standalone extract_content() function is forbidden. MUST use HTMLExtractor class with extract() method.",
                            "suggestion": "Remove extract_content() function and use HTMLExtractor.extract() method instead"
                        })
                    
                    # Check for forbidden method names in HTMLExtractor class
                    if not is_standalone and func_name in ['extract_from_string', 'extract_from_file']:
                        issues.append({
                            "type": "ForbiddenMethodName",
                            "severity": "high",
                            "message": f"Method '{func_name}' is forbidden. MUST use 'extract' method only.",
                            "suggestion": "Rename to 'extract' method with signature: extract(self, html_content: Optional[str] = None, file_path: Optional[str] = None) -> Dict[str, Any]"
                        })
            
            # Must have HTMLExtractor class (extract_content function is NOT allowed)
            if html_extractor_class is None:
                issues.append({
                    "type": "MissingHTMLExtractorClass",
                    "severity": "high",
                    "message": "Code MUST define 'HTMLExtractor' class with 'extract' method",
                    "suggestion": "Add HTMLExtractor class with __init__(self, schema: Dict[str, Any], logger: Optional[logging.Logger] = None) -> None and extract(self, html_content: Optional[str] = None, file_path: Optional[str] = None) -> Dict[str, Any]"
                })
            
            # Check if extract method returns Dict (not ExtractionResult or other types)
            if extract_method:
                # Check return type more strictly
                if extract_method.returns:
                    return_type_str = ast.unparse(extract_method.returns) if hasattr(ast, 'unparse') else str(extract_method.returns)
                    # Check for forbidden return types
                    forbidden_types = ['ExtractionResult', 'dataclass', 'List[', 'Tuple[']
                    for forbidden in forbidden_types:
                        if forbidden in return_type_str:
                            issues.append({
                                "type": "InvalidReturnType",
                                "severity": "high",
                                "message": f"extract() method MUST return Dict[str, Any], found: {return_type_str}",
                                "suggestion": "Change return type to: -> Dict[str, Any] (plain dictionary, not dataclass or other types)"
                            })
            
            # Check for SCHEMA constant (optional but recommended)
            has_schema_constant = False
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == 'SCHEMA':
                            has_schema_constant = True
                            break
            
            if not has_schema_constant:
                warnings.append({
                    "type": "MissingSchemaConstant",
                    "severity": "low",
                    "message": "Consider defining SCHEMA constant at module level for better structure",
                    "suggestion": "Add: SCHEMA: Dict[str, Any] = {...} at module level"
                })
            
        except SyntaxError:
            # If code has syntax errors, skip interface checking
            # Syntax errors are already caught in _check_syntax
            pass
        except Exception as e:
            logger.warning(f"Error during interface compliance check: {e}")
            warnings.append({
                "type": "InterfaceCheckError",
                "severity": "low",
                "message": f"Could not complete interface compliance check: {str(e)}",
                "suggestion": "Manual review recommended"
            })
        
        return {"issues": issues, "warnings": warnings}
    
    def _ai_code_review(self, code: str, validation_result: Dict[str, Any], json_schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Use AI to review code and provide suggestions or fixes
        """
        try:
            # Build review prompt
            prompt = self._build_review_prompt(code, validation_result, json_schema)
            
            if self.client_type == 'anthropic':
                # Use maximum tokens supported (128000), leave small buffer
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=127000,
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
                review_text = ""
                for block in response.content:
                    if block.type == "text":
                        review_text = block.text
            else:
                # Use maximum tokens supported (128000), leave small buffer for safety
                # Set to 127000 to ensure we don't exceed the limit
                max_tokens = 127000
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt()},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.2,
                    max_tokens=max_tokens
                )
                
                review_text = response.choices[0].message.content
            
            # Parse AI response
            return self._parse_ai_review(review_text, code)
            
        except Exception as e:
            logger.error(f"AI code review failed: {e}")
            return {"suggestions": [], "fixed_code": None}
    
    def _build_review_prompt(self, code: str, validation_result: Dict[str, Any], json_schema: Optional[Dict[str, Any]] = None) -> str:
        """
        Build prompt for AI code review
        """
        issues_summary = []
        if validation_result.get("syntax_errors"):
            issues_summary.append(f"Syntax Errors: {len(validation_result['syntax_errors'])}")
            for err in validation_result["syntax_errors"][:3]:  # Show first 3
                issues_summary.append(f"  - {err.get('type')}: {err.get('message')}")
        
        if validation_result.get("robustness_issues"):
            issues_summary.append(f"Robustness Issues: {len(validation_result['robustness_issues'])}")
            for issue in validation_result["robustness_issues"][:3]:
                issues_summary.append(f"  - {issue.get('type')}: {issue.get('message')}")
        
        if validation_result.get("interface_issues"):
            issues_summary.append(f"Interface Compliance Issues: {len(validation_result['interface_issues'])}")
            for issue in validation_result["interface_issues"][:3]:
                issues_summary.append(f"  - {issue.get('type')}: {issue.get('message')}")
        
        schema_context = ""
        if json_schema:
            import json
            schema_context = f"\n\nJSON Schema Context:\n{json.dumps(json_schema, indent=2, ensure_ascii=False)[:1000]}"
        
        return f"""Review and fix the following Python code for HTML content extraction.

Issues Found:
{chr(10).join(issues_summary) if issues_summary else "No critical issues found"}

Code to Review:
```python
{code}
```
{schema_context}

Please:
1. Fix any syntax errors
2. Address robustness issues (error handling, None checks, etc.)
3. Fix interface compliance issues (function signatures, return types)
4. Ensure code follows Python best practices
5. Use proper path handling (pathlib.Path or raw strings)
6. Replace any JSON boolean values (true/false) with Python booleans (True/False)
7. Add proper error handling where needed

CRITICAL INTERFACE REQUIREMENTS (MUST BE STRICTLY ENFORCED):
- MUST define class named exactly 'HTMLExtractor' (case-sensitive)
- HTMLExtractor.__init__() MUST have EXACT signature: __init__(self, schema: Dict[str, Any], logger: Optional[logging.Logger] = None) -> None
- Parameter name MUST be exactly 'schema' (not json_schema, not extraction_schema)
- MUST have method named exactly 'extract' (NOT extract_from_string, extract_from_file, extract_content, etc.)
- extract() method MUST have EXACT signature: extract(self, html_content: Optional[str] = None, file_path: Optional[str] = None) -> Dict[str, Any]
- Parameter names MUST be exactly 'html_content' and 'file_path' (no variations)
- extract() method MUST return Dict[str, Any] (plain dictionary, NOT ExtractionResult, NOT dataclass, NOT list, NOT other types)
- DO NOT create methods named extract_from_string, extract_from_file, extract_content, etc.
- DO NOT return custom result types (ExtractionResult, dataclass, etc.)

Return the fixed code in a markdown code block, and provide a brief summary of changes made."""
    
    def _get_system_prompt(self) -> str:
        return """You are an expert Python code reviewer specializing in code quality, robustness, and best practices.
Your role is to identify and fix syntax errors, improve error handling, and ensure code follows Python conventions.
Focus on making code production-ready, robust, and maintainable."""
    
    def _parse_ai_review(self, review_text: str, original_code: str) -> Dict[str, Any]:
        """
        Parse AI review response to extract suggestions and fixed code
        """
        suggestions = []
        fixed_code = None
        
        # Try multiple patterns to extract code from markdown code blocks
        # Pattern 1: ```python ... ``` or ```python3 ... ```
        code_match = re.search(r'```(?:python|python3)?\s*(.*?)```', review_text, re.DOTALL)
        if code_match:
            fixed_code = code_match.group(1).strip()
        else:
            # Pattern 2: Look for code block without language specifier
            code_match = re.search(r'```\s*(.*?)```', review_text, re.DOTALL)
            if code_match:
                fixed_code = code_match.group(1).strip()
        
        # Clean up the extracted code
        if fixed_code:
            # Remove any remaining markdown artifacts
            fixed_code = fixed_code.strip()
            
            # Remove any remaining ``` markers that might be in the code
            fixed_code = re.sub(r'^```+\s*', '', fixed_code, flags=re.MULTILINE)
            fixed_code = re.sub(r'\s*```+$', '', fixed_code, flags=re.MULTILINE)
            
            # Remove leading/trailing whitespace
            fixed_code = fixed_code.strip()
            
            # Validate that the extracted code is actually Python code
            # Check if it looks like Python (has Python keywords or structure)
            if not any(keyword in fixed_code for keyword in ['def ', 'import ', 'class ', 'from ', 'if ', 'return ']):
                logger.warning("Extracted code doesn't look like Python, may be invalid")
                # Try to find actual code in the response
                # Look for code after "Here's the fixed code:" or similar markers
                code_after_marker = re.search(
                    r'(?:fixed code|corrected code|updated code|here.*?code)[:\n]+(.*?)(?:\n\n|\Z)', 
                    review_text, 
                    re.DOTALL | re.IGNORECASE
                )
                if code_after_marker:
                    potential_code = code_after_marker.group(1).strip()
                    # Remove markdown code blocks from potential code
                    potential_code = re.sub(r'```(?:python|python3)?\s*', '', potential_code)
                    potential_code = re.sub(r'```\s*', '', potential_code)
                    potential_code = potential_code.strip()
                    if len(potential_code) > 100:  # Reasonable code length
                        fixed_code = potential_code
        
        # Extract suggestions from text
        lines = review_text.split('\n')
        for line in lines:
            if line.strip().startswith('-') or line.strip().startswith('*'):
                suggestions.append(line.strip())
        
        # If no valid code found, use original code
        if not fixed_code or len(fixed_code) < 100:
            logger.warning("No valid fixed code extracted from AI response, using original code")
            fixed_code = original_code
        else:
            # Validate syntax of extracted code
            try:
                import ast
                ast.parse(fixed_code)
                logger.info("Extracted fixed code passes syntax validation")
            except SyntaxError as e:
                logger.error(f"Extracted fixed code has syntax errors: {e}")
                logger.warning("Using original code instead")
                fixed_code = original_code
        
        return {
            "suggestions": suggestions,
            "fixed_code": fixed_code
        }
    
    def fix_code(self, code: str, validation_result: Dict[str, Any]) -> str:
        """
        Attempt to automatically fix code based on validation results
        """
        fixed_code = code
        
        # Auto-fix common issues
        # Fix JSON boolean values
        fixed_code = re.sub(r':\s*false\s*([,}])', r': False\1', fixed_code)
        fixed_code = re.sub(r':\s*true\s*([,}])', r': True\1', fixed_code)
        
        # Fix invalid escape sequences in string literals (basic fix)
        # This is complex, so we'll rely on AI for most fixes
        
        # Use AI-fixed code if available
        if validation_result.get("fixed_code"):
            fixed_code = validation_result["fixed_code"]
        
        return fixed_code

