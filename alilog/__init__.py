"""
alilog - 阿里云 SLS Console 日志查询 CLI。

本包提供命令行工具用于查询阿里云日志服务（SLS）的日志。

主要功能：
- 日志查询（search）：支持多种时间格式和分页
- 上下文查询（context）：查看日志的上下文
- 浏览器认证（auth login）：自动从浏览器提取认证信息

使用方式：
    alilog search --project my-project --logstore my-logstore --query "error" --last 1h
    alilog context --pack-meta "..." --pack-id "..."
    alilog auth login
"""

__all__ = ["__version__"]

__version__ = "0.3.2"
