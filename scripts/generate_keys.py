"""
卡密生成脚本
用于批量生成卡密并输出为JSON格式，可直接用于替换 license.py 中的 DEFAULT_KEY_REGISTRY
"""

import json
import random
import string
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict


def generate_key(prefix: str = "JD", length: int = 8, use_date: bool = True) -> str:
    """
    生成单个卡密
    
    Args:
        prefix: 卡密前缀，默认为 "JD"
        length: 随机字符长度，默认为 8
        use_date: 是否在卡密中包含年份，默认为 True
    
    Returns:
        生成的卡密字符串，格式如：JD-XXXX-2025 或 JD-XXXXXXXX
    """
    # 生成随机字符（大写字母和数字）
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
) -> List[Dict[str, str]]:
    """
    批量生成卡密
    
    Args:
        count: 生成卡密数量
        expiry_date: 过期日期，格式：YYYY-MM-DD
        prefix: 卡密前缀，默认为 "JD"
        length: 随机字符长度，默认为 8
        use_date: 是否在卡密中包含年份，默认为 True
        output_file: 输出文件路径（可选），如果提供则保存到文件
    
    Returns:
        卡密字典列表，格式：[{"key": "JD-XXXX-2025", "expiry": "2025-12-31"}, ...]
    """
    # 验证日期格式
    try:
        datetime.strptime(expiry_date, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"日期格式错误，应为 YYYY-MM-DD，例如：2025-12-31")
    
    keys = []
    generated = set()  # 用于去重
    
    print(f"正在生成 {count} 个卡密...")
    print(f"过期日期: {expiry_date}")
    print(f"卡密格式: {prefix}-{'XXXX-' if use_date else 'XXXX'}{datetime.now().year if use_date else ''}")
    print("-" * 60)
    
    while len(keys) < count:
        key = generate_key(prefix, length, use_date)
        
        # 确保不重复
        if key not in generated:
            generated.add(key)
            keys.append({"key": key, "expiry": expiry_date})
            print(f"[{len(keys)}/{count}] {key}")
    
    # 转换为字典格式（用于替换 DEFAULT_KEY_REGISTRY）
    registry_dict = {item["key"]: item["expiry"] for item in keys}
    
    # 输出到控制台
    print("\n" + "=" * 60)
    print("生成的卡密字典（可直接复制到 license.py 的 DEFAULT_KEY_REGISTRY）:")
    print("=" * 60)
    print(json.dumps(registry_dict, ensure_ascii=False, indent=2))
    
    # 如果指定了输出文件，保存到文件
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 保存为字典格式（用于替换代码）
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(registry_dict, f, ensure_ascii=False, indent=2)
        
        print(f"\n卡密已保存到: {output_path.absolute()}")
        
        # 同时保存为列表格式（便于查看）
        list_output_path = output_path.parent / f"{output_path.stem}_list.json"
        with list_output_path.open("w", encoding="utf-8") as f:
            json.dump(keys, f, ensure_ascii=False, indent=2)
        print(f"列表格式已保存到: {list_output_path.absolute()}")
    
    return keys


def main():
    """主函数，提供交互式界面"""
    print("=" * 60)
    print("卡密生成工具")
    print("=" * 60)
    print()
    
    try:
        # 获取用户输入
        count = int(input("请输入要生成的卡密数量: "))
        if count <= 0:
            raise ValueError("卡密数量必须大于 0")
        
        expiry_date = input("请输入过期日期 (格式: YYYY-MM-DD，例如: 2025-12-31): ").strip()
        if not expiry_date:
            raise ValueError("过期日期不能为空")
        
        prefix = input("请输入卡密前缀 (默认: JD，直接回车使用默认值): ").strip() or "JD"
        
        length_input = input("请输入随机字符长度 (默认: 8，直接回车使用默认值): ").strip()
        length = int(length_input) if length_input else 8
        if length < 4:
            print("警告: 随机字符长度过短，建议至少 4 位")
        
        use_date_input = input("是否在卡密中包含年份? (Y/n，默认: Y): ").strip().lower()
        use_date = use_date_input != 'n'
        
        output_file = input("请输入输出文件路径 (可选，直接回车跳过): ").strip()
        output_file = output_file if output_file else None
        
        print()
        
        # 生成卡密
        keys = generate_keys(
            count=count,
            expiry_date=expiry_date,
            prefix=prefix,
            length=length,
            use_date=use_date,
            output_file=output_file
        )
        
        print()
        print("=" * 60)
        print(f"成功生成 {len(keys)} 个卡密！")
        print("=" * 60)
        
    except KeyboardInterrupt:
        print("\n\n操作已取消")
    except Exception as e:
        print(f"\n错误: {e}")


if __name__ == "__main__":
    main()

