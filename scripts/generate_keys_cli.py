"""
卡密生成脚本（命令行版本）
用法示例:
    python generate_keys_cli.py --count 10 --expiry 2025-12-31
    python generate_keys_cli.py --count 20 --expiry 2026-06-30 --prefix JD --output keys.json
"""

import argparse
import json
import random
import string
from datetime import datetime
from pathlib import Path
from typing import Dict


def generate_key(prefix: str = "JD", length: int = 8, use_date: bool = True) -> str:
    """生成单个卡密"""
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
    
    if use_date:
        year = datetime.now().year
        return f"{prefix}-{random_part}-{year}"
    else:
        return f"{prefix}-{random_part}"


def generate_keys(
    count: int,
    expiry_date: str,
    prefix: str = "JD",
    length: int = 8,
    use_date: bool = True,
    output_file: str = None
) -> Dict[str, str]:
    """批量生成卡密"""
    # 验证日期格式
    try:
        datetime.strptime(expiry_date, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"日期格式错误，应为 YYYY-MM-DD，例如：2025-12-31")
    
    registry_dict = {}
    generated = set()
    
    print(f"正在生成 {count} 个卡密...")
    print(f"过期日期: {expiry_date}")
    print(f"卡密格式: {prefix}-{'XXXX-' if use_date else 'XXXX'}{datetime.now().year if use_date else ''}")
    print("-" * 60)
    
    while len(registry_dict) < count:
        key = generate_key(prefix, length, use_date)
        
        if key not in generated:
            generated.add(key)
            registry_dict[key] = expiry_date
            print(f"[{len(registry_dict)}/{count}] {key}")
    
    # 输出到控制台
    print("\n" + "=" * 60)
    print("生成的卡密字典（可直接复制到 license.py 的 DEFAULT_KEY_REGISTRY）:")
    print("=" * 60)
    print(json.dumps(registry_dict, ensure_ascii=False, indent=2))
    
    # 保存到文件
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(registry_dict, f, ensure_ascii=False, indent=2)
        
        print(f"\n卡密已保存到: {output_path.absolute()}")
    
    return registry_dict


def main():
    parser = argparse.ArgumentParser(
        description="卡密生成工具（命令行版本）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 生成10个卡密，过期日期2025-12-31
  python generate_keys_cli.py --count 10 --expiry 2025-12-31
  
  # 生成20个卡密，自定义前缀和输出文件
  python generate_keys_cli.py --count 20 --expiry 2026-06-30 --prefix JD --output keys.json
  
  # 生成卡密，不包含年份
  python generate_keys_cli.py --count 5 --expiry 2025-12-31 --no-date
        """
    )
    
    parser.add_argument(
        "--count", "-c",
        type=int,
        required=True,
        help="要生成的卡密数量"
    )
    
    parser.add_argument(
        "--expiry", "-e",
        type=str,
        required=True,
        help="过期日期，格式: YYYY-MM-DD (例如: 2025-12-31)"
    )
    
    parser.add_argument(
        "--prefix", "-p",
        type=str,
        default="JD",
        help="卡密前缀 (默认: JD)"
    )
    
    parser.add_argument(
        "--length", "-l",
        type=int,
        default=8,
        help="随机字符长度 (默认: 8)"
    )
    
    parser.add_argument(
        "--no-date",
        action="store_true",
        help="不在卡密中包含年份"
    )
    
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="输出文件路径 (可选)"
    )
    
    args = parser.parse_args()
    
    if args.count <= 0:
        parser.error("卡密数量必须大于 0")
    
    if args.length < 4:
        print("警告: 随机字符长度过短，建议至少 4 位")
    
    try:
        registry_dict = generate_keys(
            count=args.count,
            expiry_date=args.expiry,
            prefix=args.prefix,
            length=args.length,
            use_date=not args.no_date,
            output_file=args.output
        )
        
        print()
        print("=" * 60)
        print(f"成功生成 {len(registry_dict)} 个卡密！")
        print("=" * 60)
        
    except Exception as e:
        print(f"错误: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())

