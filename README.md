# plamoindex

`plamoindex` 用来生成塑料模型说明书和产品元数据索引。它会从官方站点采集数据，也支持人工补充其他厂商的产品和说明书信息，最后输出一组静态 JSON 文件，供其他项目读取。

当前自动采集来源：

- Bandai 说明书站
- Bandai 日文、英文、中文发售表
- Kotobukiya 说明书和产品页

人工补充来源：

- `curated/vendors/`：补充说明书数据
- `curated/products/`：补充产品元数据

## 快速开始

安装依赖：

```bash
pip install -e ".[dev]"
```

查看可用数据源：

```bash
plamoindex sources list
```

校验人工维护的数据：

```bash
plamoindex curated validate curated/
```

采集并构建数据：

```bash
plamoindex sync --source all --curated curated/ --raw data/raw/ --dist dist/
```

校验输出：

```bash
plamoindex validate --dist dist/
```

## 手动添加产品

推荐用交互式命令添加产品，减少手写 YAML 的出错概率：

```bash
plamoindex curated product add --curated curated/
```

命令会询问厂商、产品编号、名称、价格、发售时间、系列、比例、关联说明书等字段，然后写入：

```text
curated/products/<source_id>.yaml
```

如果同一个厂商文件已经存在，新产品会追加到现有文件里。生成后命令会自动校验该文件。

如果库里已经有相同厂商、系列或比例，命令会显示编号列表让你直接选择；没有合适选项时，直接输入新值即可。

也可以直接编辑 YAML。示例：

```yaml
source_id: hasegawa
display_name: Hasegawa
manufacturer: HASEGAWA
locale: ja
market: jp

products:
  - product_id: bk-001
    title: "1/72 VF-1 Valkyrie"
    manufacturer_item_code: "BK-001"
    product_url: "https://example.com/products/bk-001"
    image_url: "https://example.com/products/bk-001.jpg"
    category: "plastic model"
    brand_line: "Macross"
    series: "Macross"
    release_month: "2026-06"
    price_amount: 3200
    price_currency: JPY
    price_tax_included: true
    specs:
      scale: "1/72"
    manual_source_keys:
      - hasegawa:bk-001-manual
```

`manual_source_keys` 是可选字段。填写后，构建时会自动把产品和对应说明书关联起来。

## 手动添加说明书

说明书数据放在：

```text
curated/vendors/<source_id>.yaml
```

示例：

```yaml
source_id: hasegawa
display_name: Hasegawa
source_type: curated

records:
  - manual_source_key: hasegawa:bk-001-manual
    manual_source_id: bk-001-manual
    title: "1/72 VF-1 Valkyrie Manual"
    brand: "HASEGAWA"
    pdf_url: "https://example.com/manuals/bk-001.pdf"
    languages: ["ja"]
```

产品和说明书可以分别添加。只要产品里的 `manual_source_keys` 指向说明书的 `manual_source_key`，最终输出里就会有它们的关系。

## 外部贡献流程

其他人想提交产品数据时，流程很简单：

1. Fork 这个仓库
2. 新增或修改 `curated/products/*.yaml`
3. 如有说明书数据，同步新增或修改 `curated/vendors/*.yaml`
4. 本地运行校验：

```bash
plamoindex curated validate curated/
```

5. 提交 Pull Request

PR CI 会自动检查人工数据、运行测试，并做一次不联网的构建校验。贡献者不需要提交 `dist/` 或 `data/raw/`。

## GitHub Actions

仓库里有两个主要 workflow：

- `CI`：在 push 和 Pull Request 时运行，检查测试、类型、lint、人工数据和一次本地构建。
- `Dataset Build`：手动或定时运行，采集线上数据，合并人工数据，生成最终 `dist/`，并部署到 GitHub Pages。

如果要手动回溯 Bandai 发售表，可以在 `Dataset Build` 的手动运行参数里填写：

```text
bandai_schedule_start_month = 198007
bandai_schedule_end_month   = 202612
```

这个月份范围会同时应用到 Bandai 日文、英文、中文发售表。

大范围历史回填不会一次性采完。默认每次最多处理 36 个月，避免 GitHub Actions 超过 6 小时被终止：

```text
bandai_schedule_max_months_per_run = 36
```

如果要补齐 `198007` 到 `202612`，重复用同一组参数运行 `Dataset Build` 即可。项目会利用 `data/raw` 缓存记住已经采过的月份和详情页，后续运行会继续处理下一批缺失月份，并把新数据合并进已有缓存。

回填会按“语言站点 + 月份”独立推进。中文站默认从 `1989-09` 开始，早于这个月份的中文空页面会直接跳过；日文和英文仍按你填写的起止月份处理。

不建议把 `bandai_schedule_max_months_per_run` 调得过大。这个值越大，单次 workflow 越容易超时；一般保持默认值即可。

## 输出

构建完成后，主要输出在 `dist/`：

- `manuals.latest.json`：说明书数据
- `products.latest.json`：产品数据
- `relationships.v1.json`：说明书和产品的关系
- `index.json`：数据集索引和文件入口
- `checksums.json`：文件校验值

还有按来源拆分的文件，例如 Bandai、Kotobukiya、curated 产品文件。下游项目通常从 `index.json` 开始读取即可。

## 数据使用注意事项

说明书和产品是两类不同的数据，不要混在一起去重：

- `manuals.latest.json` 和 compact 说明书数据：用 `manual_source_key` 去重。
- `products.latest.json`：用 `product_key` 去重。
- `relationships.v1.json`：负责连接说明书和产品，用 `from_key`、`to_key` 和 `relationship` 表达关系。

不要用 `product_key` 去重说明书。一个产品可能有多份官方说明书，例如不同语言版本；这些说明书应该保留为多条 manual，再通过 relationships 指向同一个 product。

## 本地开发检查

修改代码后运行：

```bash
ruff check src/ tests/
mypy src/
python -m pytest
```

只改人工数据时，至少运行：

```bash
plamoindex curated validate curated/
```

## 许可证

MIT
