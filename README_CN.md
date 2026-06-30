# BA-Units

以 JSON 格式提取 **游戏《[断箭 (Broken Arrow)](https://store.steampowered.com/app/644960/Broken_Arrow/)》的单位数据**

由于单位数据加密存储，本项目将其解密并转换为纯文本的 JSON 文件，方便阅读与二次开发。此外，项目还包含了生成这些文件的 Python 脚本，以便更新。

> 🇺🇸 [English](README.md)

---

## 数据说明

所有有用的数据都位于 [`output/`](output/) 目录下：

| 文件 | 说明 |
| --- | --- |
| [`output/tables/<Table>.json`](output/tables/) | 按游戏数据表划分，每个表一个文件——包含数据行（单位、武器、装甲、传感器等）的 JSON 数组。 |
| [`output/database.json`](output/database.json) | 包含所有数据表的单个文件，格式为：`{ "TableName": [ rows… ] }`。 |
| [`output/localization/<lang>.json`](output/localization/) | 扁平化的 `{ key: text }` 映射表，用于将数据表中的 ID 转换为可读名称。 |

共包含 **24 张数据表**：

> Units, Abilities, UnitAbilities, Ammunitions, Armors, Mobility, PlaneFlyPresets,
> UnitPropulsions, Countries, Turrets, TurretUnits, Weapons, TurretWeapons,
> WeaponAmmunitions, SensorUnits, Sensors, SquadMembers, SquadWeapons, Modifications,
> Options, UnitArmors, SpecializationAvailabilities, Specializations,
> TransportAvailabilities

字段名称与游戏自身的数据模型一致，单行数据示例如下：

```json
{ "Id": 1, "Name": "Russia", "UIName": "Russia",
  "FlagFileName": "rus flag", "MaxPoints": 10000,
  "Hidden": false, "ContentMembership": -1 }

```

**如果只需获取数据：** 直接使用 `output/` 目录下的文件即可，无需运行任何代码。

---

## 自行重新生成数据

当需要在游戏更新后刷新数据，或者想验证数据是如何生成时：

```bash
pip install -r requirements.txt

# 1. 将单位数据库解密为 JSON
python tools/extract_database.py --combined

# 2. 构建本地化映射表（默认导出英文；使用 --all 导出所有语言）
python tools/extract_localization.py

```

### 所需的本地源文件

以下文件需要从你自己的游戏副本中提取，本项目**不**包含这些文件：

| 文件说明 | 来源路径 |
| --- | --- |
| 加密的单位数据库 | `ExportedProject/Assets/Resources/DataBaseCompiled.asset` |
| 本地化文本 | `ExportedProject/Assets/TextAsset/keys.json` + `<lang>.json` |
| 原生代码（仅在恢复密钥时需要） | `GameAssembly.dll` + `il2cpp_data/Metadata/global-metadata.dat` |

你可以使用 [AssetRipper](https://github.com/AssetRipper/AssetRipper) 导出游戏资源，从而获取 `ExportedProject/` 目录。

---

## 原理简述

单位数据库是一个单独的加密 Unity 资产文件。每张数据表的存储格式为：

```
Base64( "fhk3s0g3" + IV(16 字节) + AES-256-CBC( JSON 数据 ) )

```

解密密钥硬编码在游戏的原生代码中，而非资产文件中。该密钥已通过 [Il2CppDumper](https://github.com/Perfare/Il2CppDumper) 提取。密钥和标记（marker）作为参数传递给脚本，因此即使游戏更新后密钥发生变化，也**无需修改代码**——只需传入新值即可。

完整的提取流程详见 [docs/EXTRACTION.md](docs/EXTRACTION.md)。

---

## 游戏更新后的处理

大部分补丁只修改**数据**，不改变加密方式：

```bash
# 1. 使用 AssetRipper 重新导出资产，替换 DataBaseCompiled.asset。
# 2. 重新运行提取脚本：
python tools/extract_database.py --combined

```

如果提取脚本报错提示 *"does not start with marker"*，说明开发者更换了加密密钥。你需要提取新密钥并重新运行——具体步骤见 [docs/EXTRACTION.md](docs/EXTRACTION.md#updating-after-a-patch)。

---

## 项目结构

```
tools/
  extract_database.py      解密 24 张数据表 → output/tables/*.json
  extract_localization.py  展平 keys.json + <lang>.json → { key: text } 映射表
  recover_key.py           在游戏更新后重新提取 AES 密钥
docs/
  EXTRACTION.md            格式与解密原理的详细技术文档
output/                    生成的 JSON 文件
requirements.txt

```