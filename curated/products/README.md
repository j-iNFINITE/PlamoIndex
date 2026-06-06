# 人工产品元数据

这里放人工维护的产品元数据，文件名使用 `<source_id>.yaml`。每个 YAML 文件通常对应一个厂商或一个人工数据来源。

可以直接编辑 YAML，也可以运行交互式命令：

```bash
plamoindex curated product add --curated curated/
```

命令会写入或追加 `curated/products/<source_id>.yaml`，并自动校验生成的文件。如果库里已经有厂商、系列、比例等信息，命令会显示编号列表让你选择；没有合适选项时，直接输入新值即可。

示例：

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

`manual_source_keys` 是可选字段。填写后，构建时会自动创建产品和说明书的确认关系。
