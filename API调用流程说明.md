# crawlAgent API调用流程详解

## 整体流程概览

```
输入 (HTML文件/URL列表)
    ↓
[步骤1] Analyzer Agent (文本分析)
    ↓
[步骤2] Visual Analyzer (视觉分析，可选)
    ↓
[步骤3] Orchestrator (结果综合)
    ↓
[步骤4] Orchestrator (生成JSON Schema)
    ↓
[步骤5] Code Generator (生成提取代码)
    ↓
[步骤6] Code Validator (验证代码)
    ↓
[步骤6.5] Code Execution (代码执行)
    ↓
[步骤7] Markdown Converter (Markdown 转换)
    ↓
输出 (extraction_code.py + extraction_schema.json + extraction_results/ + markdown_output/)
```

---

## 步骤1: Analyzer Agent (文本结构分析)

### 输入 (Input)
- **多个HTML文件**: 系统会处理**多个HTML文件**（不是单个）
  - 可以是目录下的所有 `.html` 文件
  - 或者从URL列表下载的多个HTML文件
- **每个文件的HTML内容**: 原始HTML字符串（如果超过50000字符会被截断）
- **文件标识**: 每个文件的路径或URL

**重要**: 系统设计为处理多个HTML文件，这样可以：
- 识别跨文件的共同结构模式
- 生成更通用、更健壮的XPath表达式
- 提高提取代码的适用性

### 调用的模型
- **模型**: `ANTHROPIC_MODEL` (默认: `claude-3-5-sonnet-20241022`)
- **API端点**: `ANTHROPIC_BASE_URL` (默认: `https://api.anthropic.com`)
- **API类型**: OpenAI兼容格式 (使用OpenAI客户端调用Anthropic API)
- **Temperature**: 0.3

### 作用 (Purpose)
深度分析HTML的文本结构，识别：
1. 主要内容区域（标题、正文、评论、元数据等）
2. XPath表达式来定位每个区域
3. 识别相似元素的模式（如所有评论项）
4. 每个区域的结构特征

### 处理方式
- **循环处理**: 对每个HTML文件分别调用API
- **每个文件一次API调用**: 如果有N个HTML文件，会进行N次API调用
- **结果汇总**: 所有文件的分析结果汇总成一个列表

### 输出 (Output)
**列表格式**，每个文件一个分析结果：
```json
[
    {
        "file": "文件路径1",
        "sections": [
        {
            "name": "section_name",
            "type": "title|body|comment|metadata|other",
            "xpath": "xpath_expression",
            "description": "区域描述",
            "is_list": false,
            "list_xpath": "列表项XPath（如适用）",
            "attributes": {"class": "...", "id": "..."},
            "content_sample": "示例内容"
        }
    ],
    "patterns": {
        "common_classes": [...],
        "common_ids": [...],
        "structural_patterns": [...]
    },
    "notes": "额外观察"
    },
    {
        "file": "文件路径2",
        "sections": [...],
        ...
    }
]
```

### 保存位置
- `flow1/step1_text_analysis_result.json`
- `flow1/checkpoint.json` (检查点)

---

## 步骤2: Visual Analyzer (视觉布局分析) - 可选

### 输入 (Input)
- **多个HTML文件**: 与步骤1相同，处理多个HTML文件
- **每个文件的HTML内容**: 原始HTML字符串
- **文件标识**: 每个文件的路径或URL

### 处理方式
- **循环处理**: 对每个HTML文件分别进行视觉分析
- **每个文件一次API调用**: 如果有N个HTML文件，会进行N次API调用
- **结果汇总**: 所有文件的视觉分析结果汇总成一个列表

### 调用的模型
- **模型**: `VISION_MODEL` (默认: `gpt-4-vision-preview`)
- **API端点**: `VISION_BASE_URL` (默认: 与OPENAI_BASE_URL相同)
- **API类型**: OpenAI Vision API
- **Temperature**: 0.3

### 作用 (Purpose)
通过渲染HTML页面并使用视觉模型分析：
1. 主要内容区域的视觉结构（header、body、sidebar、footer、评论区域等）
2. 指示内容类型的视觉模式（如评论块、文章区域）
3. 布局结构和内容组织方式
4. 重复模式（如评论项、列表项等）

### 处理流程
1. **HTML渲染**: 使用Playwright将HTML渲染为图片（1920x1080）
   - 如果Playwright失败，回退到Selenium
2. **图片编码**: 将截图转换为base64编码
3. **视觉分析**: 调用Vision API分析图片

### 输出 (Output)
**列表格式**，每个文件一个视觉分析结果：
```json
[
    {
        "file": "文件路径1",
        "visual_sections": [
        {
            "name": "section_name",
            "type": "header|body|comment|sidebar|footer|other",
            "description": "视觉描述",
            "position": "top|middle|bottom|left|right",
            "characteristics": ["视觉特征"],
            "likely_xpath_hints": ["class模式", "id模式"]
        }
    ],
    "layout_structure": "整体布局描述",
    "repeating_patterns": ["模式1", "模式2"],
    "notes": "额外视觉观察"
    },
    {
        "file": "文件路径2",
        "visual_sections": [...],
        ...
    }
]
```

### 保存位置
- `flow2/step2_visual_analysis_result.json`
- `flow2/checkpoint.json` (检查点)

---

## 步骤3: Orchestrator (结果综合)

### 输入 (Input)
- **文件列表**: 所有处理的HTML文件标识符列表
- **文本分析结果**: 步骤1的所有分析结果
- **视觉分析结果**: 步骤2的所有分析结果（如果启用）

### 调用的模型
- **模型**: `OPENAI_MODEL` (默认: `gpt-4o`)
- **API端点**: `OPENAI_BASE_URL` (默认: `https://api.openai.com/v1`)
- **API类型**: OpenAI Chat API
- **Temperature**: 0.3

### 作用 (Purpose)
综合所有分析结果，识别：
1. 跨所有文件的共同结构模式
2. 关键内容区域（标题、正文、评论等）
3. 跨多个文件工作的XPath模式
4. 不一致性或边缘情况

### 输出 (Output)
JSON格式的综合结果：
```json
{
    "common_patterns": [...],
    "content_sections": [...],
    "xpath_patterns": [...],
    "inconsistencies": [...]
}
```

### 保存位置
- `flow3/step3_synthesized_result.json`
- `flow3/checkpoint.json` (检查点)

---

## 步骤4: Orchestrator (生成JSON Schema)

### 输入 (Input)
- **综合分析结果**: 步骤3的综合结果

### 调用的模型
- **模型**: `OPENAI_MODEL` (默认: `gpt-4o`)
- **API端点**: `OPENAI_BASE_URL` (默认: `https://api.openai.com/v1`)
- **API类型**: OpenAI Chat API
- **Temperature**: 0.2 (更低温度，更确定性)
- **Response Format**: 尝试使用 `{"type": "json_object"}` (如果API支持)

### 作用 (Purpose)
基于所有分析结果生成最终的JSON Schema，包含：
1. 关键内容区域的XPath路径
2. 每个区域代表的描述（如"评论"、"文章正文"、"标题"）
3. 识别相似元素的模式
4. 结构相关的元数据

### 输出 (Output)
JSON Schema格式：
```json
{
    "schema_version": "1.0",
    "description": "从HTML页面提取内容的模式",
    "sections": [
        {
            "name": "section_name",
            "description": "区域描述",
            "xpath": "xpath_expression",
            "xpath_list": ["xpath1", "xpath2", ...],
            "is_list": true/false,
            "attributes": {"key": "value"},
            "notes": "额外说明"
        }
    ],
    "metadata": {
        "total_sections": 数量,
        "extraction_notes": "..."
    }
}
```

### 保存位置
- `flow4/extraction_schema.json`
- `flow4/step4_schema_result.json`
- `flow4/checkpoint.json` (检查点)

---

## 步骤5: Code Generator (生成提取代码)

### 输入 (Input)
- **JSON Schema**: 步骤4生成的完整JSON Schema

### 调用的模型
根据配置选择：
- **选项A (Anthropic)**: 
  - 模型: `ANTHROPIC_MODEL` (默认: `claude-3-5-sonnet-20241022`)
  - API端点: `ANTHROPIC_BASE_URL`
  - 支持Thinking模式（budget_tokens: 10000）
  
- **选项B (OpenAI)**:
  - 模型: `OPENAI_MODEL` (默认: `gpt-4o`)
  - API端点: `OPENAI_BASE_URL`
  - Max Tokens: 16000
  - Timeout: 300秒

### 作用 (Purpose)
根据JSON Schema生成生产就绪的Python提取代码：
1. 使用lxml进行HTML解析
2. 实现基于XPath的健壮提取
3. 优雅处理缺失元素
4. 返回结构化数据（字典/JSON）
5. 包含错误处理
6. 支持批量处理多个HTML文件

### 处理逻辑
- 如果Schema过大（>100KB），会简化Schema以减少prompt大小
- 包含重试逻辑（最多3次，指数退避）
- 如果API失败，会生成fallback代码模板

### 输出 (Output)
完整的Python代码文件，包含：
- 所有必要的imports
- HTMLContentExtractor类
- extract()方法（支持文件路径或HTML字符串）
- extract_batch()方法（批量处理）
- main()函数示例

### 保存位置
- `flow5/extraction_code.py`
- `flow5/checkpoint.json` (检查点)

---

## 步骤6: Code Validator (代码验证)

### 输入 (Input)
- **生成的代码**: 步骤5生成的Python代码
- **JSON Schema**: 步骤4的Schema（用于上下文）

### 调用的模型
根据配置选择（与Code Generator相同）：
- **选项A (Anthropic)**: `ANTHROPIC_MODEL`
- **选项B (OpenAI)**: `OPENAI_MODEL`

### 作用 (Purpose)
验证和改进生成的代码：
1. **语法验证**: 使用AST解析器检查Python语法
2. **健壮性检查**: 静态分析检查错误处理、None检查等
3. **AI代码审查**: 使用AI提供改进建议和修复

### 验证内容
- 语法错误（SyntaxError）
- 无效转义序列
- JSON布尔值在Python代码中（true/false → True/False）
- 缺少错误处理
- 缺少None检查
- 缺少空列表检查
- 缺少必要的imports
- 硬编码路径

### 输出 (Output)
验证结果JSON：
```json
{
    "valid": true/false,
    "syntax_errors": [...],
    "robustness_issues": [...],
    "suggestions": [...],
    "fixed_code": "修复后的代码（如果有）",
    "warnings": [...]
}
```

### 自动修复
- 如果发现问题，会尝试自动修复
- 使用AI生成的修复代码（如果可用）
- 自动替换JSON布尔值为Python布尔值

### 保存位置
- `output/code_validation_result.json`
- 修复后的代码会更新 `output/extraction_code.py`

---

## 步骤6.5: Code Execution (代码执行)

### 输入 (Input)
- **验证后的代码**: 步骤6验证并修复后的 `extraction_code.py`
- **JSON Schema**: 步骤4的Schema（用于上下文）
- **HTML文件**: `data/input/spread/html/` 目录下的所有HTML文件
  - 或者从 `data/input/spread/urls.txt` 下载的HTML文件

### 处理方式
- **动态导入**: 使用 `importlib` 动态加载生成的提取代码
- **批量处理**: 对 spread 目录下的所有HTML文件执行提取
- **每个文件独立结果**: 为每个HTML文件生成独立的JSON结果文件

### 作用 (Purpose)
执行验证后的提取代码，从HTML文件中提取结构化数据：
1. 动态加载生成的 `HTMLExtractor` 类
2. 对每个HTML文件调用 `extract()` 方法
3. 将提取结果保存为独立的JSON文件
4. 生成提取结果汇总文件

### 处理流程
1. **加载代码模块**: 使用 `importlib.util.spec_from_file_location()` 加载代码
2. **实例化提取器**: 创建 `HTMLExtractor()` 实例
3. **处理每个文件**: 
   - 读取HTML文件内容
   - 调用 `extractor.extract(file_path=...)` 或 `extractor.extract(html_content=...)`
   - 获取提取结果（字典格式）
4. **保存结果**: 
   - 每个HTML文件对应一个JSON文件（如 `page1.json`）
   - 保存到 `flow6/extraction_results/` 目录
5. **生成汇总**: 创建 `extraction_results_summary.json` 包含所有处理文件的信息

### 输出 (Output)
**目录结构**:
```
flow6/
├── extraction_code.py (已验证的代码)
├── extraction_results/
│   ├── page1.json          # 第一个HTML的提取结果
│   ├── page2.json          # 第二个HTML的提取结果
│   └── ...
└── extraction_results_summary.json  # 汇总文件
```

**汇总文件格式**:
```json
{
    "total_files": 5,
    "processed_files": 5,
    "failed_files": 0,
    "extraction_results_directory": "extraction_results",
    "results": [
        {
            "html_file": "page1.html",
            "json_file": "page1.json",
            "status": "success"
        },
        ...
    ]
}
```

### 保存位置
- `flow6/extraction_results/`: 包含所有提取结果的JSON文件
- `flow6/extraction_results_summary.json`: 提取结果汇总
- `flow6/checkpoint.json`: 更新检查点（包含执行结果信息）

### 错误处理
- 如果代码加载失败，记录错误并跳过
- 如果某个文件提取失败，记录错误但继续处理其他文件
- 所有错误信息都会记录在汇总文件中

---

## 步骤7: Markdown Converter (Markdown 转换)

### 输入 (Input)
- **JSON提取结果**: 步骤6.5生成的所有JSON结果文件（`flow6/extraction_results/*.json`）
- **内容分析**: 分析JSON结果以识别主要内容字段

### 调用的模型
根据配置选择（与Analyzer相同）：
- **选项A (Anthropic)**: 
  - 模型: `ANTHROPIC_MODEL` (默认: `claude-3-5-sonnet-20241022`)
  - API端点: `ANTHROPIC_BASE_URL`
  
- **选项B (OpenAI)**: 
  - 模型: `ANTHROPIC_MODEL` (通过OpenAI兼容接口)
  - API端点: `ANTHROPIC_BASE_URL`
  - Temperature: 0.3
  - Max Tokens: 4000 (内容分析) / 8000 (代码生成)

### 作用 (Purpose)
将JSON提取结果转换为Markdown格式：
1. **内容分析**: 分析JSON结果识别主要内容字段（正文、标题、元数据等）
2. **生成转换代码**: 生成Python代码将JSON转换为Markdown
3. **执行转换**: 对每个JSON文件执行转换，生成Markdown文件

### 处理流程

#### 子步骤7.1: 内容分析 (Content Analysis)
- **输入**: 采样3个JSON结果文件进行分析
- **API调用**: 1次
- **输出**: 内容字段分析结果（识别主要内容、元数据、结构字段等）

#### 子步骤7.2: 生成转换代码 (Generate Converter Code)
- **输入**: 内容分析结果 + 示例JSON结构
- **API调用**: 1次
- **输出**: `MarkdownConverter` 类的Python代码
- **接口要求**:
  - 类名必须为 `MarkdownConverter`
  - 必须有 `convert(json_data: Dict[str, Any]) -> str` 方法
  - 返回Markdown格式的字符串

#### 子步骤7.3: 执行转换 (Execute Conversion)
- **处理方式**: 本地执行，无需API调用
- **对每个JSON文件**:
  1. 加载JSON数据
  2. 实例化 `MarkdownConverter()`
  3. 调用 `converter.convert(json_data=json_data)`
  4. 保存Markdown文件（如 `page1.json` → `page1.md`）

### 输出 (Output)
**目录结构**:
```
flow7/
├── markdown_converter.py          # 生成的转换代码
├── markdown_output/
│   ├── page1.md                   # 第一个JSON的Markdown结果
│   ├── page2.md                   # 第二个JSON的Markdown结果
│   └── ...
└── markdown_conversion_summary.json  # 转换汇总
```

**汇总文件格式**:
```json
{
    "total_files": 5,
    "processed_files": 5,
    "failed_files": 0,
    "markdown_output_directory": "markdown_output",
    "results": [
        {
            "json_file": "page1.json",
            "markdown_file": "page1.md",
            "status": "success"
        },
        ...
    ]
}
```

### 保存位置
- `flow7/markdown_converter.py`: 生成的Markdown转换代码
- `flow7/markdown_output/`: 包含所有转换后的Markdown文件
- `flow7/markdown_conversion_summary.json`: 转换结果汇总
- `flow7/checkpoint.json`: 检查点（包含转换代码和结果信息）

### 代码接口要求
生成的 `MarkdownConverter` 类必须严格遵循以下接口：

```python
from typing import Dict, Any

class MarkdownConverter:
    def __init__(self) -> None:
        # 初始化，无必需参数
        pass
    
    def convert(self, json_data: Dict[str, Any]) -> str:
        # 将JSON数据转换为Markdown格式字符串
        # 参数名必须为 json_data
        # 返回类型必须为 str
        return markdown_string
```

### Markdown格式要求
- 遵循标准Markdown语法
- HTML标签转换为Markdown等价物（如 `<h1>` → `#`, `<p>` → 段落）
- 保留内容层次结构（标题、正文、列表等）
- 正确处理特殊字符转义

---

## 检查点系统 (Checkpoint System)

### 功能
- 每个步骤完成后自动保存检查点
- 支持从任何步骤恢复
- 防止进度丢失

### 检查点文件
- `flow{N}/checkpoint.json`: 每个步骤的检查点文件
  - `flow1/checkpoint.json`: 步骤1（文本分析）检查点
  - `flow2/checkpoint.json`: 步骤2（视觉分析）检查点
  - `flow3/checkpoint.json`: 步骤3（结果综合）检查点
  - `flow4/checkpoint.json`: 步骤4（Schema生成）检查点
  - `flow5/checkpoint.json`: 步骤5（代码生成）检查点
  - `flow6/checkpoint.json`: 步骤6（代码验证和执行）检查点
  - `flow7/checkpoint.json`: 步骤7（Markdown转换）检查点
- `flow{N}/step*_*.json`: 各步骤的独立结果文件

### 恢复逻辑
- **自动恢复（默认）**: 启动时自动扫描所有 `flow{N}/` 目录
- **检查点加载**: 从最新的检查点恢复所有已完成步骤的数据
- **智能跳过**: 已完成的步骤自动跳过，从第一个未完成的步骤继续
- **手动控制**: 支持 `--no-resume` 参数强制重新开始

---

## 配置说明

### 环境变量 (.env文件)

```env
# OpenAI API (用于Orchestrator和Code Generator)
OPENAI_API_KEY=sk-your_api_key_here
OPENAI_API_BASE=http://your-endpoint:port/v1
OPENAI_MODEL=gpt-4o-mini

# Anthropic API (用于Analyzer)
ANTHROPIC_API_KEY=your_anthropic_api_key_here
ANTHROPIC_BASE_URL=https://api.anthropic.com
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022

# Vision Model API (用于Visual Analyzer)
VISION_API_KEY=sk-your_api_key_here
VISION_MODEL=gpt-4o
VISION_API_BASE=http://your-endpoint:port/v1
```

---

## 总结

### API调用次数统计

假设处理 **N个HTML文件**：

1. **Analyzer Agent**: **N次** API调用 (每个文件一次)
   - 模型: Anthropic Claude
   - 用途: 文本结构分析

2. **Visual Analyzer**: **N次** API调用 (每个文件一次，如果启用)
   - 模型: OpenAI GPT-4 Vision
   - 用途: 视觉布局分析

3. **Orchestrator (综合)**: **1次** API调用
   - 模型: OpenAI GPT-4
   - 用途: 综合所有文件的分析结果

4. **Orchestrator (Schema)**: **1次** API调用
   - 模型: OpenAI GPT-4
   - 用途: 生成最终JSON Schema

5. **Code Generator**: **1次** API调用
   - 模型: Anthropic Claude 或 OpenAI GPT-4
   - 用途: 生成提取代码

6. **Code Validator**: **1次** API调用
   - 模型: Anthropic Claude 或 OpenAI GPT-4
   - 用途: 验证代码

7. **Markdown Converter (内容分析)**: **1次** API调用
   - 模型: Anthropic Claude 或 OpenAI GPT-4
   - 用途: 分析JSON结果识别主要内容字段

8. **Markdown Converter (生成代码)**: **1次** API调用
   - 模型: Anthropic Claude 或 OpenAI GPT-4
   - 用途: 生成Markdown转换代码

**总API调用次数**: 
- 如果启用视觉分析: **2N + 6次**
- 如果不启用视觉分析: **N + 6次**

例如，处理5个HTML文件：
- 启用视觉分析: 2×5 + 6 = **16次API调用**
- 不启用视觉分析: 5 + 6 = **11次API调用**

**注意**: 步骤6.5（代码执行）和步骤7.3（执行Markdown转换）是本地执行，不需要API调用。

### 为什么处理多个文件？

系统设计为处理多个HTML文件，这样可以：
1. **识别共同模式**: 通过分析多个相似页面，识别稳定的结构模式
2. **提高健壮性**: 生成的XPath表达式能适应页面间的细微差异
3. **更好的泛化**: 提取代码能在同类页面上更好地工作
4. **减少错误**: 通过多文件验证，避免过度拟合单个页面的特殊结构

每个步骤都有独立的检查点，支持断点续传，确保即使中途失败也不会丢失已完成的步骤结果。

