# fixed-width-record-loader

Python 定长记录接入库，处理多版布局、编码边界、派生字段和坏记录隔离。

## 字段宽度单位：字节

**布局中所有 `start` / `length` 一律以字节（byte）为单位，不是字符数。**
这是本库与旧系统"按字符截取"的本质区别：中文姓名在 GBK 下占 2 字节、
UTF-8 下占 3 字节，按字符截取会导致整行字段错位。本库的处理顺序是：

1. 按 CRLF / LF / CR 切出物理行，记录每行的原始字节偏移；
2. 按记录类型码（字节区间）选择布局；
3. 先按**字节偏移**切片，再对每个字段的字节段按布局编码解码；
4. 切片若落在多字节字符中间，该字段解码失败，整条记录被隔离为坏记录，
   绝不让错位扩散到后续字段。

## 布局版本

`fixedwidth/layouts.py` 内置两个版本，可用 `get_version(name)` 获取：

- `V2009`：GBK 编码，金额符号位在前（`sign="leading"`），无补充字段；
- `V2015`：UTF-8 编码，金额符号位在后（`sign="trailing"`），
  明细行超长部分按补充字段（memo）解析。

自定义版本只需构造 `LayoutVersion`：编码、记录类型码位置、
各记录类型的 `FieldSpec`（字节偏移/宽度/类型/符号位/隐含小数位）、
尾部校验字段映射和 `DerivedRule` 派生规则（abs / sub / concat / sign）。

## 加载语义

```python
from fixedwidth.layouts import get_version
from fixedwidth.loader import FileLoader, UploadRegistry

sink = lambda records, header, trailer: save_to_db(records)
loader = FileLoader(get_version("V2015"), sink, UploadRegistry("registry.json"))
result = loader.load(open("D20150630.dat", "rb").read(), "D20150630.dat")
```

- **原子提交**：明细先解析到暂存区，只有尾部笔数与金额合计校验通过后
  才调用 `sink`；校验失败整文件拒绝，不会部分提交。
- **坏记录隔离**：短行、超长行（无补充字段时）、金额非法、多字节解码失败、
  未知记录类型都会被隔离，`result.bad_records` 中携带原始字节偏移、
  行号、原因和原始字节。
- **重传幂等**：`UploadRegistry` 按文件名登记内容摘要。相同文件名相同内容
  直接幂等跳过（`duplicate`）；相同文件名不同内容拒绝覆盖（`rejected`）；
  校验失败的文件不登记，修正后可重传。

## 样本与测试

```bash
python -m samples.generate_samples   # 用代码生成 V2009/V2015 多版布局样本
python -m unittest                   # 运行全部单元测试
```

样本覆盖：CRLF/LF 行尾、短行、超长行（补充字段）、GBK/UTF-8 中文混合、
正负金额（符号位在前/在后）、派生字段、尾部校验失败和同名重传。
