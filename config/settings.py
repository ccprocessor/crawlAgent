import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """
    Centralized configuration settings
    """
    
    # ==================== 路径配置 ====================
    # 项目根目录
    PROJECT_ROOT = Path(__file__).parent.parent.resolve()
    
    # 数据目录（所有输入输出的基础目录）
    DATA_DIR = Path(os.getenv('DATA_DIR', PROJECT_ROOT / 'data')).resolve()
    
    # 输入目录
    INPUT_DIR = DATA_DIR / 'input'
    
    # 学习内容目录（typcial - 智能体需要学习的内容）
    # 支持两种输入方式：
    # 1. urls.txt - URL列表文件，需要先爬取
    # 2. html/ - 已爬取好的HTML文件目录
    TYPICAL_DIR = INPUT_DIR / 'typcial'
    TYPICAL_URLS_FILE = TYPICAL_DIR / 'urls.txt'
    TYPICAL_HTML_DIR = TYPICAL_DIR / 'html'
    
    # 执行目录（spread - 生成的代码执行时处理的内容）
    # 注意：这不是智能体的输入，而是生成的代码执行时的输入目录
    # 支持两种输入方式：
    # 1. urls.txt - URL列表文件
    # 2. html/ - HTML文件目录
    SPREAD_DIR = INPUT_DIR / 'spread'
    SPREAD_URLS_FILE = SPREAD_DIR / 'urls.txt'
    SPREAD_HTML_DIR = SPREAD_DIR / 'html'
    
    # 输出目录（每次调用API的结果存储位置）
    # 如果环境变量设置了 OUTPUT_DIR，使用环境变量的值
    # 否则默认使用 DATA_DIR / 'output'
    _output_dir_env = os.getenv('OUTPUT_DIR')
    if _output_dir_env:
        # 如果环境变量是相对路径，基于 DATA_DIR 解析
        _output_path = Path(_output_dir_env)
        if not _output_path.is_absolute():
            OUTPUT_DIR = (DATA_DIR / _output_dir_env).resolve()
        else:
            OUTPUT_DIR = _output_path.resolve()
    else:
        OUTPUT_DIR = (DATA_DIR / 'output').resolve()
    
    # 流程输出目录（支持多个流程，每个流程有独立的输出目录）
    # 格式：output/flow{N}/ 其中N为流程编号
    @classmethod
    def get_flow_output_dir(cls, flow_id: int = 1) -> Path:
        """
        获取指定流程的输出目录
        
        Args:
            flow_id: 流程编号，默认为1
            
        Returns:
            Path: 流程输出目录路径
        """
        flow_dir = cls.OUTPUT_DIR / f'flow{flow_id}'
        flow_dir.mkdir(parents=True, exist_ok=True)
        return flow_dir
    
    @classmethod
    def get_next_flow_id(cls) -> int:
        """
        获取下一个可用的流程编号（自动递增）
        扫描 output 目录下已存在的 flow 文件夹，返回下一个可用的编号
        
        Returns:
            int: 下一个可用的流程编号
        """
        if not cls.OUTPUT_DIR.exists():
            return 1
        
        # 扫描已存在的 flow 文件夹
        existing_flows = []
        for item in cls.OUTPUT_DIR.iterdir():
            if item.is_dir() and item.name.startswith('flow'):
                try:
                    # 提取 flow 后面的数字
                    flow_num = int(item.name[4:])  # 'flow' 是4个字符
                    existing_flows.append(flow_num)
                except ValueError:
                    # 如果无法解析数字，跳过
                    continue
        
        if not existing_flows:
            return 1
        
        # 返回最大的编号 + 1
        return max(existing_flows) + 1
    
    @classmethod
    def get_next_flow_output_dir(cls) -> Path:
        """
        获取下一个可用的流程输出目录（自动创建新的 flow 文件夹）
        
        Returns:
            Path: 下一个可用的流程输出目录路径
        """
        next_flow_id = cls.get_next_flow_id()
        return cls.get_flow_output_dir(next_flow_id)
    
    # ==================== API配置 ====================
    # OpenAI settings
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    # Support both OPENAI_API_BASE and OPENAI_BASE_URL for compatibility
    # Use exactly as user configured, no modification
    OPENAI_BASE_URL = os.getenv('OPENAI_API_BASE') or os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o')
    
    # Anthropic settings
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
    # Use exactly as user configured, no modification
    ANTHROPIC_BASE_URL = os.getenv('ANTHROPIC_BASE_URL', 'https://api.anthropic.com')
    ANTHROPIC_MODEL = os.getenv('ANTHROPIC_MODEL', 'claude-3-5-sonnet-20241022')
    
    # Vision settings - use same base_url as OpenAI
    VISION_API_KEY = os.getenv('VISION_API_KEY') or OPENAI_API_KEY
    VISION_MODEL = os.getenv('VISION_MODEL', 'gpt-4-vision-preview')
    # Support both VISION_API_BASE and VISION_BASE_URL for compatibility
    # Use exactly as user configured, no modification
    VISION_BASE_URL = os.getenv('VISION_API_BASE') or os.getenv('VISION_BASE_URL', OPENAI_BASE_URL)
    
    # ==================== 其他配置 ====================
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    @classmethod
    def initialize_directories(cls) -> None:
        """
        初始化并创建所有必需的目录结构
        """
        directories = [
            cls.DATA_DIR,
            cls.INPUT_DIR,
            cls.TYPICAL_DIR,
            cls.TYPICAL_HTML_DIR,
            cls.SPREAD_DIR,
            cls.SPREAD_HTML_DIR,
            cls.OUTPUT_DIR,
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def validate(cls) -> bool:
        """
        Validate that required settings are present
        """
        # 初始化目录结构
        cls.initialize_directories()
        
        # 验证API密钥
        if not cls.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required")
        if not cls.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is required")
        return True
    
    @classmethod
    def get_path_info(cls) -> dict:
        """
        获取所有路径配置信息（用于调试和文档）
        
        Returns:
            dict: 路径配置字典
        """
        return {
            'project_root': str(cls.PROJECT_ROOT),
            'data_dir': str(cls.DATA_DIR),
            'input_dir': str(cls.INPUT_DIR),
            'typical_dir': str(cls.TYPICAL_DIR),
            'typical_urls_file': str(cls.TYPICAL_URLS_FILE),
            'typical_html_dir': str(cls.TYPICAL_HTML_DIR),
            'spread_dir': str(cls.SPREAD_DIR),
            'spread_urls_file': str(cls.SPREAD_URLS_FILE),
            'spread_html_dir': str(cls.SPREAD_HTML_DIR),
            'output_dir': str(cls.OUTPUT_DIR),
        }

