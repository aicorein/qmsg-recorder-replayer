import sqlite3

# 连接到 SQLite 数据库（如果数据库不存在，会自动创建）
conn = sqlite3.connect("../src/replayer/databases/messages/messages.db")
cursor = conn.cursor()

# 查询数据（你可以在这里填写自己的 SQL 查询语句）
query_sql = "select count(*) from segments"  # 示例查询语句
cursor.execute(query_sql)

# 获取查询结果
results = cursor.fetchall()

# 打印查询结果
print("查询结果：")
for row in results:
    print(row)

cursor.close()
conn.close()
