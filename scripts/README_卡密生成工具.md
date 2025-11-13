# 卡密生成工具使用说明

本工具用于批量生成卡密，生成的卡密可以直接用于替换 `JD_Live_Assistant/core/license.py` 中的 `DEFAULT_KEY_REGISTRY`。

## 文件说明

- `generate_keys.py` - 交互式版本，运行后会提示输入参数
- `generate_keys_cli.py` - 命令行版本，支持通过命令行参数直接运行
- `generate_keys.bat` - Windows批处理文件，双击即可运行交互式版本

## 使用方法

### 方法一：交互式版本（推荐新手）

**Windows用户：**
双击运行 `scripts/generate_keys.bat`

**或使用命令行：**
```bash
python scripts/generate_keys.py
```

运行后会依次提示输入：
- 卡密数量
- 过期日期（格式：YYYY-MM-DD）
- 卡密前缀（默认：JD）
- 随机字符长度（默认：8）
- 是否包含年份（默认：是）
- 输出文件路径（可选）

### 方法二：命令行版本（推荐批量操作）

```bash
# 基本用法：生成10个卡密，过期日期2025-12-31
python scripts/generate_keys_cli.py --count 10 --expiry 2025-12-31

# 自定义前缀和输出文件
python scripts/generate_keys_cli.py --count 20 --expiry 2026-06-30 --prefix JD --output keys.json

# 不包含年份的卡密
python scripts/generate_keys_cli.py --count 5 --expiry 2025-12-31 --no-date

# 自定义随机字符长度
python scripts/generate_keys_cli.py --count 10 --expiry 2025-12-31 --length 10
```

**命令行参数说明：**
- `--count, -c`: 要生成的卡密数量（必需）
- `--expiry, -e`: 过期日期，格式 YYYY-MM-DD（必需）
- `--prefix, -p`: 卡密前缀（默认：JD）
- `--length, -l`: 随机字符长度（默认：8）
- `--no-date`: 不在卡密中包含年份
- `--output, -o`: 输出文件路径（可选）

## 输出格式

生成的卡密会以字典格式输出，例如：

```json
{
  "JD-A1B2C3D4-2025": "2025-12-31",
  "JD-E5F6G7H8-2025": "2025-12-31",
  "JD-I9J0K1L2-2025": "2025-12-31"
}
```

## 如何使用生成的卡密

### 方式一：直接替换代码中的字典

1. 运行生成脚本，复制输出的JSON字典
2. 打开 `JD_Live_Assistant/core/license.py`
3. 找到 `DEFAULT_KEY_REGISTRY` 变量（约第32行）
4. 将生成的字典内容替换进去

**示例：**
```python
DEFAULT_KEY_REGISTRY: Dict[str, str] = {
    "JD-A1B2C3D4-2025": "2025-12-31",
    "JD-E5F6G7H8-2025": "2025-12-31",
    "JD-I9J0K1L2-2025": "2025-12-31",
}
```

### 方式二：使用输出文件

如果指定了 `--output` 参数，生成的卡密会保存到JSON文件中，可以：
1. 打开生成的JSON文件
2. 复制内容到 `DEFAULT_KEY_REGISTRY`
3. 或者修改代码，从文件加载卡密（需要修改 `LicenseManager` 的初始化逻辑）

## 卡密格式说明

- **默认格式**：`JD-XXXXXXXX-YYYY`（前缀-8位随机字符-年份）
- **不包含年份**：`JD-XXXXXXXX`（前缀-8位随机字符）
- 随机字符由大写字母和数字组成（A-Z, 0-9）
- 卡密会自动转换为大写进行验证

## 注意事项

1. **随机字符长度**：建议至少4位，过短可能导致重复
2. **日期格式**：必须使用 `YYYY-MM-DD` 格式，例如 `2025-12-31`
3. **卡密唯一性**：脚本会自动去重，确保不会生成重复的卡密
4. **过期日期**：卡密在过期日期的23:59:59之前仍然有效

## 示例场景

### 场景1：生成月度卡密
```bash
python scripts/generate_keys_cli.py --count 50 --expiry 2025-12-31 --output monthly_keys.json
```

### 场景2：生成年度卡密
```bash
python scripts/generate_keys_cli.py --count 100 --expiry 2026-12-31 --output yearly_keys.json
```

### 场景3：生成测试卡密
```bash
python scripts/generate_keys_cli.py --count 5 --expiry 2025-12-31 --prefix TEST --output test_keys.json
```

## 故障排除

**问题：找不到Python**
- 确保已安装Python 3.7+
- 或使用虚拟环境：`venv\Scripts\python.exe scripts/generate_keys.py`

**问题：日期格式错误**
- 确保使用 `YYYY-MM-DD` 格式，例如：`2025-12-31`，不是 `2025/12/31`

**问题：生成的卡密重复**
- 增加随机字符长度（`--length` 参数）
- 减少生成数量

