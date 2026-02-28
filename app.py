import os
import time
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from aip import AipOcr
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = 'nju_invoice_assistant_secret_key'

# ==========================================
# 1. 核心配置区 (Supabase + 百度API)
# ==========================================

# 连接 Supabase PostgreSQL 云数据库
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:nandajinglin@db.qjwfamlhmtriaqvycnbr.supabase.co:5432/postgres'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# 连接 Supabase Storage 云存储桶
SUPABASE_URL = "https://qjwfamlhmtriaqvycnbr.supabase.co"
SUPABASE_KEY = "sb_publishable_7GAGR_O7WftZvdonzdaw_Q_BS1Ngtru"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 百度 OCR 配置 (🚨 请在这里填入你真实的百度秘钥！)
APP_ID = '122001991'
API_KEY = 'aE4bjyOR0B0JWQxhGvtMhTMh'
SECRET_KEY = 'PCMvnAFiL1gXg2y2Q3q2LYjSFu02fZwUY'
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
        
        # 2. 调用百度 API 提取发票数据
        res = ocr_client.vatInvoice(file_bytes)
        
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
            for i in range(len(words['CommodityName'])):
                item = InvoiceItem(
                    invoice_id=new_inv.id,
                    name=words['CommodityName'][i].get('word', '') if i < len(words['CommodityName']) else '',
                    spec=words['CommodityType'][i].get('word', '') if 'CommodityType' in words and i < len(words['CommodityType']) else '',
                    unit=words['CommodityUnit'][i].get('word', '') if 'CommodityUnit' in words and i < len(words['CommodityUnit']) else '',
                    quantity=words['CommodityNum'][i].get('word', '') if 'CommodityNum' in words and i < len(words['CommodityNum']) else '',
                    price=words['CommodityPrice'][i].get('word', '') if 'CommodityPrice' in words and i < len(words['CommodityPrice']) else '',
                    amount=words['CommodityAmount'][i].get('word', '') if 'CommodityAmount' in words and i < len(words['CommodityAmount']) else '',
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