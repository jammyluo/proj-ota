#!/usr/bin/env python3
"""
OTA Version Update Script

用于更新应用版本和生成配置文件。
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# 从环境变量读取配置，提供默认值
APPS_DIR = Path(os.getenv('APPS_DIR', 'apps'))
BASE_URL = os.getenv('BASE_URL', 'http://localhost:3000')
RESTART_CMD = os.getenv('RESTART_CMD', '')

# 确保应用目录存在
APPS_DIR.mkdir(parents=True, exist_ok=True)


def log(level, message, *args):
    """日志函数"""
    timestamp = datetime.now().isoformat()
    print(f"[{timestamp}] [{level}] {message}", *args)


def info(message, *args):
    log('INFO', message, *args)


def error(message, *args):
    log('ERROR', message, *args)
    sys.exit(1)


def calculate_sha256(file_path):
    """计算文件的 SHA256 校验和"""
    sha256_hash = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for byte_block in iter(lambda: f.read(4096), b''):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def copy_binary(source_path, app_name, apps_dir):
    """复制文件到应用的二进制目录"""
    source = Path(source_path)
    if not source.exists():
        error(f'Binary file not found: {source_path}')
    
    # 确保应用目录结构存在: apps/<app_name>/files/
    app_dir = apps_dir / app_name
    app_binary_dir = app_dir / 'files'
    app_binary_dir.mkdir(parents=True, exist_ok=True)
    info(f'Created files directory for app {app_name}: {app_binary_dir}')
    
    target_path = app_binary_dir / source.name
    
    # 复制文件
    shutil.copy2(source, target_path)
    
    # 确保文件可执行（Unix 系统）
    if os.name != 'nt':
        os.chmod(target_path, 0o755)
    
    info(f'Copied binary to: {target_path}')
    return target_path


def generate_yaml_config(files, version, app_name, restart_cmd=None):
    """生成 YAML 配置文件"""
    yaml_lines = [f'version: "{version}"', 'files:']
    
    for file in files:
        yaml_lines.append(f'  - name: "{file["name"]}"')
        yaml_lines.append(f'    url: "{file["url"]}"')
        yaml_lines.append(f'    sha256: "{file["sha256"]}"')
        yaml_lines.append(f'    target: "{file["target"]}"')
        if file.get('version') and file['version'] != version:
            yaml_lines.append(f'    version: "{file["version"]}"')
    
    if restart_cmd:
        yaml_lines.append(f"restart_cmd: '{restart_cmd}'")
    
    return '\n'.join(yaml_lines) + '\n'


def main():
    parser = argparse.ArgumentParser(
        description='OTA Version Update Script',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 多文件
  %(prog)s myapp 1.0.0 \\
    --file ./app1:app1:/usr/bin/app1:false \\
    --file ./app2:app2:/usr/bin/app2:true

  # 使用 JSON 配置文件
  %(prog)s myapp 1.0.0 --config files.json

JSON 配置文件格式:
  {
    "files": [
      {
        "path": "./app1",
        "name": "app1",
        "target": "/usr/bin/app1",
      }
    ],
    "restart_cmd": "systemctl restart myapp"  # 可选
  }

环境变量:
  APPS_DIR       应用目录 (默认: ./apps)
  BASE_URL       服务器基础 URL (默认: http://localhost:3000)
  RESTART_CMD    全局重启命令 (可选，如果配置文件中未指定)
        """
    )
    
    parser.add_argument('app_name', nargs='?', help='应用名称')
    parser.add_argument('version', nargs='?', help='版本号 (例如: 1.0.0)')
    parser.add_argument('-a', '--app', dest='app_name_opt', help='应用名称')
    parser.add_argument('-v', '--version', dest='version_opt', help='版本号')
    parser.add_argument('-f', '--file', action='append', dest='files',
                       help='文件规格: path:name:target (例如: ./app:main:/usr/bin/app)')
    parser.add_argument('-c', '--config', help='JSON 配置文件路径（多文件配置）')
    
    args = parser.parse_args()
    
    # 确定应用名称和版本
    app_name = args.app_name_opt or args.app_name
    version = args.version_opt or args.version
    
    if not app_name:
        error('App name is required. Use --app or provide as first argument.')
    
    if not version:
        error('Version is required. Use --version or provide as second argument.')
    
    # 加载文件配置
    files = []
    restart_cmd_from_config = None
    if args.config:
        # 从 JSON 配置文件加载
        try:
            with open(args.config, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            if 'files' in config_data and isinstance(config_data['files'], list):
                files = config_data['files']
            else:
                error('Invalid config file format: files array is required')
            # 从配置文件获取 restart_cmd（如果存在）
            if 'restart_cmd' in config_data:
                restart_cmd_from_config = config_data['restart_cmd']
        except Exception as e:
            error(f'Failed to read config file: {e}')
    elif args.files:
        # 从命令行参数解析
        for file_spec in args.files:
            parts = file_spec.split(':')
            if len(parts) < 1:
                continue
            file_path = parts[0]
            file_name = parts[1] if len(parts) > 1 else Path(file_path).name
            file_target = parts[2] if len(parts) > 2 else ''
            file_restart = parts[3] in ('true', '1') if len(parts) > 3 else False
            files.append({
                'path': file_path,
                'name': file_name,
                'target': file_target
            })
    
    if not files:
        error('At least one file is required. Use --file or --config.')
    
    info('Starting version update...')
    info(f'App name: {app_name}')
    info(f'Version: {version}')
    info(f'Files: {len(files)}')
    info(f'Apps directory: {APPS_DIR}')
    info(f'Base URL: {BASE_URL}')
    
    # 复制所有文件并准备配置
    file_configs = []
    for file in files:
        if 'path' not in file:
            error(f'File path is required for file: {file.get("name", "unknown")}')
        
        # 复制文件到应用目录
        binary_path = copy_binary(file['path'], app_name, APPS_DIR)
        file_name = binary_path.name
        
        # 确定目标路径
        target_path = file.get('target')
        if not target_path:
            target_path = f'/usr/local/bin/{file.get("name", file_name)}'
            info(f'No target specified for {file.get("name", file_name)}, using default: {target_path}')
        
        # 计算 SHA256
        sha256 = calculate_sha256(binary_path)
        
        file_configs.append({
            'name': file.get('name', file_name),
            'url': f'{BASE_URL}/ota/{app_name}/files/{file_name}',
            'sha256': sha256,
            'target': target_path,
            'version': version
        })
    
    # 确定 restart_cmd：优先使用配置文件中的，否则使用环境变量
    restart_cmd = restart_cmd_from_config if restart_cmd_from_config is not None else RESTART_CMD
    
    # 生成配置
    try:
        yaml_content = generate_yaml_config(file_configs, version, app_name, restart_cmd)
        
        # 写入应用配置文件: apps/<app_name>/version.yaml
        app_dir = APPS_DIR / app_name
        app_dir.mkdir(parents=True, exist_ok=True)
        config_file = app_dir / 'version.yaml'
        config_file.write_text(yaml_content, encoding='utf-8')
        info(f'Configuration updated: {config_file}')
        
        # 显示配置信息
        print('\n📋 Configuration:')
        print(f'  App Name:   {app_name}')
        print(f'  Version:    {version}')
        print(f'  Files:      {len(file_configs)}')
        for file in file_configs:
            print(f'    - {file["name"]}: {file["url"]} -> {file["target"]}')
        if restart_cmd:
            print(f'  Restart Cmd: {restart_cmd}')
        print(f'\n📡 Config URL: {BASE_URL}/ota/{app_name}/version.yaml')
        print('\n✅ Version update completed successfully!')
        
    except Exception as e:
        error(f'Failed to generate config: {e}')


if __name__ == '__main__':
    main()

