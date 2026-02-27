import sqlite3
import pandas as pd
import os

def fetch_reimbursement_data():
    # 连接到队长的数据库
    db_path = os.path.join('instance', 'invoices_pro.db')
    if not os.path.exists(db_path):
        print("未找到数据库，请确认是否已上传解析过发票。")
        return []
    
    conn = sqlite3.connect(db_path)
    
    # 联合查询：提取表单需要的所有关键字段
    query = """
    SELECT 
        i.payer AS 垫付人, 
        i.stu_id AS 学号, 
        i.bank_card AS 银行卡号,
        i.seller AS 供应商,
        i.inv_num AS 发票号,
        i.date AS 开票日期,
        i.folder_path AS 附件路径,
        it.name AS 商品名称,
        it.spec AS 规格型号,
        it.unit AS 单位,
        it.quantity AS 数量,
        it.price AS 单价,
        it.amount AS 总金额
    FROM invoice i
    LEFT JOIN invoice_item it ON i.id = it.invoice_id
    """
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # 把数据转换成列表字典，方便 Playwright 循环读取
    return df.to_dict('records')

if __name__ == "__main__":
    data = fetch_reimbursement_data()
    print(f"成功从发票仓库提取了 {len(data)} 条待填报商品！")
    for row in data:
        print(row)