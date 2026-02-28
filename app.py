import os
import time
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from aip import AipOcr
from supabase import create_client, Client
from flask import Flask, render_template, request, redirect, url_for, flash, send_file


app = Flask(__name__)
app.secret_key = 'nju_invoice_assistant_secret_key'

# ==========================================
# 1. 核心配置区 (Supabase + 百度API)
# ==========================================

# 连接 Supabase PostgreSQL 云数据库
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres.qjwfamlhmtriaqvycnbr:nandajinglin@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# 连接 Supabase Storage 云存储桶
SUPABASE_URL = "https://qjwfamlhmtriaqvycnbr.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFqd2ZhbWxobXRyaWFxdnljbmJyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzIyNzgwMTEsImV4cCI6MjA4Nzg1NDAxMX0.w1LGDsrFDq_TR3YTLAbY5wkOInJx4YNNHJF4cBAtxgQ"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 百度 OCR 配置 (🚨 请在这里填入你真实的百度秘钥！)
APP_ID = '122001991'
API_KEY = 'aE4bjyOR0B0JWQxhGvtMhTMh'
SECRET_KEY = 'PCMvnAFiL1gXg2y2Q3q2LYjSFu02fZwU'
ocr_client = AipOcr(APP_ID, API_KEY, SECRET_KEY)

# ==========================================
# 2. 数据库模型定义
# ==========================================

class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    payer = db.Column(db.String(50))
    stu_id = db.Column(db.String(50))
    bank_card = db.Column(db.String(50))
    seller = db.Column(db.String(255))
    inv_num = db.Column(db.String(50))
    inv_code = db.Column(db.String(50))
    date = db.Column(db.String(50))
    total_amount = db.Column(db.String(50))
    file_url = db.Column(db.String(500))  # 存放云端图片的公网 URL
    items = db.relationship('InvoiceItem', backref='invoice', lazy=True, cascade="all, delete-orphan")

class InvoiceItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'))
    name = db.Column(db.String(255))
    spec = db.Column(db.String(255))
    unit = db.Column(db.String(50))
    quantity = db.Column(db.String(50))
    price = db.Column(db.String(50))
    amount = db.Column(db.String(50))
    tax_rate = db.Column(db.String(50))
    tax = db.Column(db.String(50))

# 自动在云端创建数据表
with app.app_context():
    db.create_all()

# ==========================================
# 3. 路由与核心业务逻辑
# ==========================================

@app.route('/')
def index():
    invoices = Invoice.query.order_by(Invoice.id.desc()).all()
    return render_template('index.html', invoices=invoices)

@app.route('/upload', methods=['POST'])
def upload():
    payer = request.form.get('payer', '')
    stu_id = request.form.get('stu_id', '')
    bank_card = request.form.get('bank_card', '')
    
    if 'invoice' not in request.files:
        flash("没有检测到文件上传！")
        return redirect(url_for('index'))
        
    file = request.files['invoice']
    if file.filename == '':
        flash("文件名不能为空！")
        return redirect(url_for('index'))

    # 读取图片字节数据
    file_bytes = file.read()
    
    try:
        # 1. 上传图片到 Supabase Storage
        filename = f"{int(time.time())}_{secure_filename(file.filename)}"
        # content-type 确保浏览器能直接预览图片而不是下载
        supabase.storage.from_("invoices").upload(filename, file_bytes, {"content-type": file.content_type})
        file_url = supabase.storage.from_("invoices").get_public_url(filename)
        
# 2. 调用百度 API 提取发票数据 (纯原生 HTTP 请求)
        import urllib.request
        import urllib.parse
        import json
        import base64
        
        # 白嫖 SDK 自动管理的鉴权 Token
        token_info = ocr_client._auth()
        access_token = token_info.get('access_token', '')
        
        # 组装纯正的原生网络请求
        request_url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/vat_invoice?access_token={access_token}"
        payload = {'image': base64.b64encode(file_bytes).decode('utf-8')}
        data = urllib.parse.urlencode(payload).encode('utf-8')
        
        req = urllib.request.Request(request_url, data=data)
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')
        
        # 发起强力穿透请求并解析返回数据
        response = urllib.request.urlopen(req)
        res = json.loads(response.read().decode('utf-8'))
        if 'words_result' not in res:
            flash(f"发票识别失败：{res.get('error_msg', '未知错误')}")
            return redirect(url_for('index'))
            
        words = res['words_result']
        
        # 3. 数据存入 Supabase PostgreSQL 数据库
        new_inv = Invoice(
            payer=payer,
            stu_id=stu_id,
            bank_card=bank_card,
            seller=words.get('SellerName', ''),
            inv_num=words.get('InvoiceNum', ''),
            inv_code=words.get('InvoiceCode', ''),
            date=words.get('InvoiceDate', ''),
            total_amount=words.get('AmountInFiguers', ''),
            file_url=file_url # 保存云端链接
        )
        db.session.add(new_inv)
        db.session.flush() # 获取插入后的主键 ID
        
# 解析明细列表
        if isinstance(words.get('CommodityName'), list):
            
            # 增加一个安全转浮点数的小工具函数
            def parse_float(val_str):
                try: return float(str(val_str).replace(',', '').replace('¥', '').strip())
                except: return 0.0

            for i in range(len(words['CommodityName'])):
                # 提前抓取并计算含税金额 (不含税金额 + 税额)
                raw_amt = words['CommodityAmount'][i].get('word', '0') if 'CommodityAmount' in words and i < len(words['CommodityAmount']) else '0'
                raw_tax = words['CommodityTax'][i].get('word', '0') if 'CommodityTax' in words and i < len(words['CommodityTax']) else '0'
                raw_qty = words['CommodityNum'][i].get('word', '0') if 'CommodityNum' in words and i < len(words['CommodityNum']) else '0'
                
                f_amt = parse_float(raw_amt)
                f_tax = parse_float(raw_tax)
                f_qty = parse_float(raw_qty)
                
                tax_incl_amt = f_amt + f_tax
                
                # 重新计算真实的含税单价
                if f_qty > 0:
                    tax_incl_price = tax_incl_amt / f_qty
                    price_val = f"{tax_incl_price:.3f}".rstrip('0').rstrip('.') if '.' in f"{tax_incl_price:.3f}" else f"{tax_incl_price}"
                else:
                    price_val = words['CommodityPrice'][i].get('word', '') if 'CommodityPrice' in words and i < len(words['CommodityPrice']) else ''
                    
                amt_val = f"{tax_incl_amt:.2f}" if tax_incl_amt > 0 else raw_amt

                item = InvoiceItem(
                    invoice_id=new_inv.id,
                    name=words['CommodityName'][i].get('word', '') if i < len(words['CommodityName']) else '',
                    spec=words['CommodityType'][i].get('word', '') if 'CommodityType' in words and i < len(words['CommodityType']) else '',
                    unit=words['CommodityUnit'][i].get('word', '') if 'CommodityUnit' in words and i < len(words['CommodityUnit']) else '',
                    quantity=raw_qty if raw_qty != '0' else '',
                    price=price_val,   # 存入真实的含税单价
                    amount=amt_val,    # 存入真实的含税金额
                    tax_rate=words['CommodityTaxRate'][i].get('word', '') if 'CommodityTaxRate' in words and i < len(words['CommodityTaxRate']) else '',
                    tax=words['CommodityTax'][i].get('word', '') if 'CommodityTax' in words and i < len(words['CommodityTax']) else ''
                )
                db.session.add(item)
                
        db.session.commit()
        flash("🎉 发票解析成功并已安全存入云端！")
        
    except Exception as e:
        db.session.rollback()
        flash(f"处理过程中发生错误: {str(e)}")
        
    return redirect(url_for('index'))


@app.route('/get_invoice_detail/<int:id>')
def get_invoice_detail(id):
    try:
        # 1. 从云端数据库查询发票和它的明细
        inv = Invoice.query.get_or_404(id)
        items = InvoiceItem.query.filter_by(invoice_id=id).all()
        
        # 2. 组装明细数据
        items_data = []
        for item in items:
            items_data.append({
                'name': item.name,
                'spec': item.spec,
                'price': item.price,
                'quantity': item.quantity,
                'amount': item.amount
            })
            
        # 3. 组装发票主数据
        inv_data = {
            'seller': inv.seller,
            'date': inv.date,
            'good_name': items[0].name if items else '详见明细',
            'spec': items[0].spec if items else '-'
        }
        
        # 4. 组装文件列表 (提取 Supabase 云端链接里的文件名)
        import urllib.parse
        raw_filename = inv.file_url.split('/')[-1] if inv.file_url else '发票原件.jpg'
        clean_filename = urllib.parse.unquote(raw_filename) # 解码中文名
        
        files_list = [{'name': clean_filename, 'protected': True}]
        
        return {"ok": True, "inv": inv_data, "items": items_data, "files_list": files_list}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.route('/preview_attachment/<int:id>')
def preview_attachment(id):
    # 预览文件时，直接重定向到 Supabase 的公网云端图片地址
    inv = Invoice.query.get_or_404(id)
    if inv.file_url:
        return redirect(inv.file_url)
    return "云端文件不存在", 404


@app.route('/download_all')
def download_all():
    import io
    import zipfile
    import openpyxl
    import urllib.request
    import urllib.parse

    invoices = Invoice.query.all()
    if not invoices:
        flash("没有可导出的发票数据！")
        return redirect(url_for('index'))

    # 在内存中创建一个 ZIP 文件
    memory_zip = io.BytesIO()
    with zipfile.ZipFile(memory_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        
# 1. 创建 Excel 汇总表
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "报销汇总"
        
        # 严格按照甲方要求的 13 个表头和顺序
        ws.append([
            '发票垫付人', '学号', '南京大学工行卡卡号', '报销商品名称', '规格型号', 
            '单位', '供应商', '发票号', '发票代码', '数量', '总金额', '单价', '开票日期'
        ])

        for inv in invoices:
            items = InvoiceItem.query.filter_by(invoice_id=inv.id).all()
            
            # 按“商品明细”循环：一张发票有2个商品，就会生成2行
            if not items:
                # 兜底：如果没有识别出明细，主信息依然保留输出
                ws.append([
                    inv.payer, inv.stu_id, inv.bank_card, '详见原件', '-', 
                    '-', inv.seller, inv.inv_num, inv.inv_code, '-', inv.total_amount, '-', inv.date
                ])
            else:
                for item in items:
                    ws.append([
                        inv.payer,          # 1. 发票垫付人
                        inv.stu_id,         # 2. 学号
                        inv.bank_card,      # 3. 南京大学工行卡卡号
                        item.name,          # 4. 报销商品名称
                        item.spec,          # 5. 规格型号
                        item.unit,          # 6. 单位
                        inv.seller,         # 7. 供应商
                        inv.inv_num,        # 8. 发票号
                        inv.inv_code,       # 9. 发票代码
                        item.quantity,      # 10. 数量
                        item.amount,        # 11. 总金额 (该商品明细的含税金额)
                        item.price,         # 12. 单价 (该商品明细的含税单价)
                        inv.date            # 13. 开票日期
                    ])

            # 3. 从 Supabase 云端拉取图片并塞入 ZIP (无需修改)
            if inv.file_url:
                try:
                    req = urllib.request.Request(inv.file_url, headers={'User-Agent': 'Mozilla/5.0'})
                    response = urllib.request.urlopen(req)
                    img_data = response.read()
                    
                    raw_filename = inv.file_url.split('/')[-1]
                    clean_filename = urllib.parse.unquote(raw_filename)
                    
                    folder_name = f"{inv.payer}_{inv.seller}_{inv.total_amount}"
                    zf.writestr(f"附件/{folder_name}/{clean_filename}", img_data)
                except Exception as e:
                    print(f"图片下载失败: {e}")

        # 4. 把存满数据的 Excel 也塞入 ZIP
        excel_memory = io.BytesIO()
        wb.save(excel_memory)
        excel_memory.seek(0)
        zf.writestr("发票汇总报表.xlsx", excel_memory.getvalue())

    # 将内存指针移回开头，准备发送给浏览器
    memory_zip.seek(0)
    
    return send_file(
        memory_zip,
        mimetype='application/zip',
        as_attachment=True,
        download_name='南大报销汇总数据_云端导出.zip'
    )


@app.route('/delete/<int:id>', methods=['POST'])
def delete_invoice(id):
    inv = Invoice.query.get_or_404(id)
    # 此处为简化逻辑，暂不调用 Supabase API 删除云端文件，只删数据库记录
    db.session.delete(inv)
    db.session.commit()
    flash("发票记录已删除！")
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Vercel 不会运行这里，这只是为了让你在本地最后测试一次
    app.run(debug=True, port=5000)