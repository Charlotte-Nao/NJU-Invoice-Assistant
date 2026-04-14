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

    warehouse_key = db.Column(db.String(50), default='main') # 新增：仓库密钥
    
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

# ======== 在这里插入新的附件表 ========
class Attachment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'))
    filename = db.Column(db.String(255))
    file_url = db.Column(db.String(500))

# 自动在云端创建数据表
with app.app_context():
    db.create_all()

# ==========================================
# 3. 路由与核心业务逻辑
# ==========================================

@app.route('/')
def index():
    # 获取当前请求的密钥，没填就默认为 main
    current_key = request.args.get('key', 'main').strip() or 'main'
    
    # 核心：只查当前密钥下的发票
    invoices = Invoice.query.filter_by(warehouse_key=current_key).order_by(Invoice.id.desc()).all()
    
    for inv in invoices:
        atts = Attachment.query.filter_by(invoice_id=inv.id).all()
        inv.has_order = any('订单' in a.filename for a in atts)
        inv.has_pay = any('支付' in a.filename for a in atts)
        
    return render_template('index.html', invoices=invoices, current_key=current_key)

@app.route('/upload', methods=['POST'])
def upload():
    payer = request.form.get('payer', '')
    stu_id = request.form.get('stu_id', '')
    bank_card = request.form.get('bank_card', '')
    # ==== 新增：获取前端传来的仓库密钥 ====
    warehouse_key = request.form.get('warehouse_key', '').strip()
    
    # 后端双重校验：如果没有填写仓库密钥，直接拦截并提示
    if not warehouse_key:
        flash("仓库密钥不能为空！")
        return redirect(url_for('index'))
    
    if 'invoice' not in request.files:
        flash("没有检测到文件上传！")
        return redirect(url_for('index', key=warehouse_key))
        
    file = request.files['invoice']
    if file.filename == '':
        flash("文件名不能为空！")
        return redirect(url_for('index', key=warehouse_key))

    # 读取图片字节数据
    file_bytes = file.read()
    
    try:
        # 1. 上传图片到 Supabase Storage
        filename = f"{int(time.time())}_{secure_filename(file.filename)}"
        supabase.storage.from_("invoices").upload(filename, file_bytes, {"content-type": file.content_type})
        file_url = supabase.storage.from_("invoices").get_public_url(filename)
        
        # 2. 调用百度 API 提取发票数据
        import urllib.request
        import urllib.parse
        import json
        import base64
        
        token_info = ocr_client._auth()
        access_token = token_info.get('access_token', '')
        request_url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/vat_invoice?access_token={access_token}"
        
        if file.filename.lower().endswith('.pdf') or file.content_type == 'application/pdf':
            payload = {'pdf_file': base64.b64encode(file_bytes).decode('utf-8')}
        else:
            payload = {'image': base64.b64encode(file_bytes).decode('utf-8')}

        data = urllib.parse.urlencode(payload).encode('utf-8')
        req = urllib.request.Request(request_url, data=data)
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')
        
        response = urllib.request.urlopen(req)
        res = json.loads(response.read().decode('utf-8'))
        if 'words_result' not in res:
            flash(f"发票识别失败：{res.get('error_msg', '未知错误')}")
            return redirect(url_for('index', key=warehouse_key))
            
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
            file_url=file_url,
            warehouse_key=warehouse_key  # ==== 新增：保存到对应密钥的仓库 ====
        )
        db.session.add(new_inv)
        db.session.flush() 
        
        # 解析明细列表
        if isinstance(words.get('CommodityName'), list):
            def parse_float(val_str):
                try: return float(str(val_str).replace(',', '').replace('¥', '').strip())
                except: return 0.0

            for i in range(len(words['CommodityName'])):
                raw_amt = words['CommodityAmount'][i].get('word', '0') if 'CommodityAmount' in words and i < len(words['CommodityAmount']) else '0'
                raw_tax = words['CommodityTax'][i].get('word', '0') if 'CommodityTax' in words and i < len(words['CommodityTax']) else '0'
                raw_qty = words['CommodityNum'][i].get('word', '0') if 'CommodityNum' in words and i < len(words['CommodityNum']) else '0'
                
                f_amt = parse_float(raw_amt)
                f_tax = parse_float(raw_tax)
                f_qty = parse_float(raw_qty)
                tax_incl_amt = f_amt + f_tax
                
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
                    price=price_val,
                    amount=amt_val,
                    tax_rate=words['CommodityTaxRate'][i].get('word', '') if 'CommodityTaxRate' in words and i < len(words['CommodityTaxRate']) else '',
                    tax=words['CommodityTax'][i].get('word', '') if 'CommodityTax' in words and i < len(words['CommodityTax']) else ''
                )
                db.session.add(item)
                
        db.session.commit()
        flash("🎉 发票解析成功并已安全存入云端！")
        
    except Exception as e:
        db.session.rollback()
        flash(f"处理过程中发生错误: {str(e)}")
        
    # ==== 核心修改：上传完跳回对应的仓库 ====
    return redirect(url_for('index', key=warehouse_key))


@app.route('/get_invoice_detail/<int:id>')
def get_invoice_detail(id):
    try:
        inv = Invoice.query.get_or_404(id)
        items = InvoiceItem.query.filter_by(invoice_id=id).all()
        atts = Attachment.query.filter_by(invoice_id=id).all() # 查询该发票的所有补充截图
        
        items_data = [{'name': item.name, 'spec': item.spec, 'price': item.price, 'quantity': item.quantity, 'amount': item.amount} for item in items]
        inv_data = {'seller': inv.seller, 'date': inv.date, 'good_name': items[0].name if items else '详见明细', 'spec': items[0].spec if items else '-'}
        
        # 组装文件列表 (发票原件 + 补充截图)
        files_list = [{'name': '发票原件.jpg', 'protected': True}]
        for att in atts:
            files_list.append({'name': att.filename, 'protected': False})
            
        # 检查是否同时拥有订单和支付截图
        has_order = any('订单' in a.filename for a in atts)
        has_pay = any('支付' in a.filename for a in atts)
        
        return {"ok": True, "inv": inv_data, "items": items_data, "files_list": files_list, "has_order": has_order, "has_pay": has_pay}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.route('/preview_attachment/<int:id>')
def preview_attachment(id):
    filename = request.args.get('filename')
    inv = Invoice.query.get_or_404(id)
    # 如果预览的是补充截图
    if filename and filename != '发票原件.jpg':
        att = Attachment.query.filter_by(invoice_id=id, filename=filename).first()
        if att and att.file_url:
            return redirect(att.file_url)
    # 否则预览发票原件
    if inv.file_url:
        return redirect(inv.file_url)
    return "云端文件不存在", 404

@app.route('/upload_extra/<int:id>', methods=['POST'])
def upload_extra(id):
    files = request.files.getlist('extra_files')
    for file in files:
        if file.filename:
            raw_filename = file.filename # 前端传来的如"订单截图_1.jpg"
            safe_name = f"extra_{id}_{int(time.time())}_{secure_filename(raw_filename)}"
            supabase.storage.from_("invoices").upload(safe_name, file.read(), {"content-type": file.content_type})
            file_url = supabase.storage.from_("invoices").get_public_url(safe_name)
            
            att = Attachment(invoice_id=id, filename=raw_filename, file_url=file_url)
            db.session.add(att)
    db.session.commit()
    return get_invoice_detail(id) # 返回刷新后的数据给前端

@app.route('/delete_attachment/<int:id>', methods=['POST'])
def delete_attachment(id):
    filename = request.form.get('filename')
    att = Attachment.query.filter_by(invoice_id=id, filename=filename).first()
    if att:
        db.session.delete(att)
        db.session.commit()
        return {"ok": True}
    return {"ok": False}

@app.route('/delete/<int:id>', methods=['GET'])
def delete_invoice(id):
    try:
        # 1. 查找对应的发票
        inv = Invoice.query.get_or_404(id)
        
        # 2. 删除该发票关联的明细 (InvoiceItem)
        db.session.query(InvoiceItem).filter_by(invoice_id=id).delete()
        
        # 3. 删除该发票关联的附件记录 (Attachment)
        db.session.query(Attachment).filter_by(invoice_id=id).delete()
        
        # 4. 删除发票主记录
        db.session.delete(inv)
        db.session.commit()
        
        # 5. 给前端 JS 返回成功信号，前端会自动移除对应的卡片
        return {"ok": True}
        
    except Exception as e:
        db.session.rollback()
        return {"ok": False, "error": str(e)}
    
@app.route('/clear_all', methods=['POST'])
def clear_all():
    # ==== 获取当前操作的仓库密钥 ====
    current_key = request.form.get('key', 'main')
    try:
        # 只找出当前仓库的发票并删除
        invs = Invoice.query.filter_by(warehouse_key=current_key).all()
        if invs:
            inv_ids = [inv.id for inv in invs]
            db.session.query(InvoiceItem).filter(InvoiceItem.invoice_id.in_(inv_ids)).delete(synchronize_session=False)
            db.session.query(Attachment).filter(Attachment.invoice_id.in_(inv_ids)).delete(synchronize_session=False)
            db.session.query(Invoice).filter(Invoice.id.in_(inv_ids)).delete(synchronize_session=False)
            db.session.commit()
        flash(f"🎉 仓库【{current_key}】的所有记录已成功清空！")
    except Exception as e:
        db.session.rollback()
        flash(f"清空失败: {str(e)}")
    return redirect(url_for('index', key=current_key))

@app.route('/download_all')
def download_all():
    import io, zipfile, openpyxl, urllib.request, os

    # ==== 获取当前操作的仓库密钥 ====
    current_key = request.args.get('key', 'main')
    invoices = Invoice.query.filter_by(warehouse_key=current_key).all()
    
    if not invoices:
        flash(f"仓库【{current_key}】没有可导出的数据！")
        return redirect(url_for('index', key=current_key))

    memory_zip = io.BytesIO()
    with zipfile.ZipFile(memory_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        # 1. 生成最外层的 Excel 汇总表
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "报销汇总"
        ws.append(['发票垫付人', '学号', '南京大学工行卡卡号', '报销商品名称', '规格型号', '单位', '供应商', '发票号', '发票代码', '数量', '总金额', '单价', '开票日期'])

        # 创建一个集合，用于记录已经写过“垫付人信息.txt”的名字，防止重复创建
        written_payers = set()

        for inv in invoices:
            items = InvoiceItem.query.filter_by(invoice_id=inv.id).all()
            
            # --- 处理 Excel 写入，并提取商品名称 ---
            if not items:
                ws.append([inv.payer, inv.stu_id, inv.bank_card, '详见原件', '-', '-', inv.seller, inv.inv_num, inv.inv_code, '-', inv.total_amount, '-', inv.date])
                goods_name = "未识别商品"
            else:
                for item in items:
                    ws.append([inv.payer, inv.stu_id, inv.bank_card, item.name, item.spec, item.unit, inv.seller, inv.inv_num, inv.inv_code, item.quantity, item.amount, item.price, inv.date])
                
                # 将同一张发票里的多个商品名称用下划线拼接起来作为文件夹名
                goods_name = "_".join([item.name for item in items if item.name])
                if not goods_name:
                    goods_name = "未识别商品"

            # --- 构建全新的文件夹层级 ---
            # 第一层：垫付人姓名文件夹
            payer_folder = f"{inv.payer}"
            
            # 如果是第一次遍历到这个垫付人，就写入他的信息txt
            if inv.payer not in written_payers:
                txt_content = f"姓名: {inv.payer}\n学号: {inv.stu_id}\n银行卡号: {inv.bank_card}\n"
                zf.writestr(f"{payer_folder}/垫付人信息.txt", txt_content.encode('utf-8'))
                written_payers.add(inv.payer)
            
            # 第二层：商品名称文件夹（带上记录ID防止同名商品覆盖）
            # 过滤掉商品名称中可能导致路径错误的特殊字符（如斜杠）
            safe_goods_name = goods_name.replace('/', '-').replace('\\', '-').replace(':', '')
            sub_folder = f"{payer_folder}/{safe_goods_name}_记录{inv.id}"
            
            # --- 抓取并写入发票原件 ---
            if inv.file_url:
                try:
                    import urllib.parse
                    raw_url_name = urllib.parse.unquote(inv.file_url.split('/')[-1])
                    ext = os.path.splitext(raw_url_name)[1]
                    if not ext: ext = '.jpg'
                    
                    img_data = urllib.request.urlopen(urllib.request.Request(inv.file_url, headers={'User-Agent': 'Mozilla/5.0'})).read()
                    zf.writestr(f"{sub_folder}/发票原件{ext}", img_data)
                except Exception as e:
                    print(f"原件下载失败: {e}")
                    
            # --- 抓取并写入附件截图 ---
            atts = Attachment.query.filter_by(invoice_id=inv.id).all()
            for att in atts:
                if att.file_url:
                    try:
                        img_data = urllib.request.urlopen(urllib.request.Request(att.file_url, headers={'User-Agent': 'Mozilla/5.0'})).read()
                        zf.writestr(f"{sub_folder}/{att.filename}", img_data)
                    except Exception as e:
                        print(f"附件下载失败: {e}")

        # 最后将 Excel 存入 ZIP 的根目录
        excel_memory = io.BytesIO()
        wb.save(excel_memory)
        zf.writestr("发票汇总报表.xlsx", excel_memory.getvalue())

    memory_zip.seek(0)
    return send_file(memory_zip, mimetype='application/zip', as_attachment=True, download_name=f'南大报销_{current_key}仓库.zip')

if __name__ == '__main__':
    # Vercel 不会运行这里，这只是为了让你在本地最后测试一次
    app.run(debug=True, port=5000)