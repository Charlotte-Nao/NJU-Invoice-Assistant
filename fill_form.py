import os
import sqlite3
import pandas as pd
from playwright.sync_api import sync_playwright

def fetch_data():
    """从队长的 SQLite 数据库中提取所有发票及商品明细数据"""
    db_path = os.path.join('instance', 'invoices_pro.db')
    if not os.path.exists(db_path):
        print("❌ 未找到数据库文件，请先在网页端上传解析发票！")
        return []
    
    conn = sqlite3.connect(db_path)
    
    # 联合查询主表(invoice)和明细表(invoice_item)
    query = """
    SELECT 
        i.payer AS 发票垫付人, 
        i.stu_id AS 学号, 
        i.bank_card AS 南京大学工行卡卡号,
        i.seller AS 供应商,
        i.inv_num AS 发票号,
        i.inv_code AS 发票代码,
        i.date AS 开票日期,
        it.name AS 报销商品名称,
        it.spec AS 规格型号,
        it.unit AS 单位,
        it.quantity AS 数量,
        it.amount AS 总金额
    FROM invoice i
    LEFT JOIN invoice_item it ON i.id = it.invoice_id
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # 清洗掉 None 或者 NaN 的数据，防止填表报错
    df = df.fillna('')
    return df.to_dict('records')

def run_bot():
    data = fetch_data()
    if not data:
        return

    print(f"✅ 成功从数据库读取到 {len(data)} 条待填报商品！")

    with sync_playwright() as p:
        # 启动 Chrome 浏览器 (headless=False 代表你能看见浏览器窗口)
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # 1. 打开问卷星链接
        form_url = "https://table.nju.edu.cn/dtable/forms/63641ff3-817d-483d-b05f-916904d143fb/"
        page.goto(form_url)
        
        # 2. 等待人工登录
        print("\n" + "="*50)
        print("🔒 请在弹出的浏览器中完成登录！")
        print("🔒 登录成功并看到【发票垫付人】输入框后，在此终端按【回车键】继续...")
        print("="*50)
        input() 

        # 3. 开始循环填表
        for i, row in enumerate(data):
            print(f"\n⚙️ 正在填写第 {i+1}/{len(data)} 条数据: {row['报销商品名称']}...")
            
            # 如果不是第一条，重新加载空表单
            if i > 0:
                page.goto(form_url)
                page.wait_for_load_state("networkidle")

            # 定义需要填写的普通文本框 (键名必须和 HTML 中的 name 属性完全一致)
            text_fields = [
                "发票垫付人", "学号", "南京大学工行卡卡号", 
                "报销商品名称", "规格型号", "单位", 
                "供应商", "发票号", "发票代码", "数量", "总金额"
            ]

            # 自动寻找输入框并打字
            for field in text_fields:
                val = str(row[field]).strip()
                if val:
                    # 这里的 input[name="xxx"] 就是根据你提供的 HTML 写出的精准定位器
                    selector = f'input[name="{field}"]'
                    try:
                        page.wait_for_selector(selector, timeout=3000)
                        page.fill(selector, val)
                    except Exception as e:
                        print(f"⚠️ 找不到【{field}】输入框，已跳过。")

            # 处理比较特殊的日期选择框
            date_val = str(row['开票日期']).strip()
            if date_val:
                try:
                    # 点击模拟唤出日期控件，并尝试键盘键入
                    page.click('div[aria-label=" 点击编辑日期"]')
                    page.keyboard.type(date_val)
                    page.keyboard.press('Enter')
                except Exception:
                    print(f"⚠️ 日期填写受阻，请手动检查一下【开票日期】: {date_val}")

            # 4. 填好后暂停，等待用户人工检查并提交
            print("\n" + "="*50)
            print(f"✅ 第 {i+1} 条数据已填写完毕！")
            print("👀 请在浏览器中检查数据是否正确。")
            print("👉 检查无误后，请手动点击网页上的【提交】按钮。")
            print("👉 提交完成后，在此终端按【回车键】开始填写下一条 (如果有的话)...")
            print("="*50)
            input() 
            
        print("\n🎉 所有报销数据已处理完毕！任务圆满结束。")
        browser.close()

if __name__ == '__main__':
    run_bot()