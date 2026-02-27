from flask import Blueprint, request, redirect, url_for, flash
from db import get_db_connection
import requests
import os

inventory_bp = Blueprint('inventory', __name__)

# ======================
# ระบบแจ้งเตือน LINE
# ======================
def send_line_notify(message):
    LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
    LINE_USER_ID = os.environ.get("LINE_USER_ID")
    
    # ถ้าไม่ได้ใส่ Token ไว้ใน .env ให้ข้ามไปเลย ระบบจะได้ไม่พัง
    if not LINE_ACCESS_TOKEN or not LINE_USER_ID:
        return

    url = 'https://api.line.me/v2/bot/message/push'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {LINE_ACCESS_TOKEN}'
    }
    data = {
        'to': LINE_USER_ID,
        'messages': [{'type': 'text', 'text': message}]
    }

    try:
        requests.post(url, headers=headers, json=data, timeout=5)
    except Exception as e:
        print(f"LINE Notify Error: {e}")

# ======================
# 1. เพิ่มพัสดุ (Add)
# ======================
@inventory_bp.route('/add_item', methods=['POST'])
def add_item():
    conn, cursor = None, None
    current_room = request.form.get('current_room')
    try:
        name = request.form['item_name']
        quantity = request.form['quantity']
        unit = request.form['unit']
        storage_id = request.form['storage_id']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO items (item_name, quantity, unit, storage_id) 
            VALUES (%s, %s, %s, %s)
        """, (name, quantity, unit, storage_id))
        
        conn.commit()
        flash(f'เพิ่มพัสดุ "{name}" สำเร็จ!', 'success')
    except Exception as e:
        if conn: conn.rollback()
        flash(f'เกิดข้อผิดพลาดในการเพิ่ม: {str(e)}', 'error')
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
            
    return redirect(url_for('dashboard.room_view', location_name=current_room) if current_room else url_for('dashboard.index'))

# ======================
# 2. เบิกของ / ตัดสต็อก (Withdraw)
# ======================
@inventory_bp.route('/withdraw_item', methods=['POST'])
def withdraw_item():
    conn, cursor = None, None
    current_room = request.form.get('current_room')
    try:
        item_id = request.form.get('item_id')
        amount = int(request.form.get('amount', 0))
        user_id = request.form.get('user_id')

        if not item_id or not user_id or amount <= 0:
            flash("ข้อมูลไม่ถูกต้อง หรือจำนวนต้องมากกว่า 0", "error")
            return redirect(url_for('dashboard.index'))

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        conn.start_transaction()

        # 🌟 ล็อคสต็อกด้วย FOR UPDATE ป้องกันคนเบิกพร้อมกัน
        cursor.execute("SELECT item_name, quantity, unit FROM items WHERE item_id = %s FOR UPDATE", (item_id,))
        item = cursor.fetchone()

        if not item or item['quantity'] < amount:
            flash(f"เบิกไม่ได้! ของเหลือไม่พอ (คงเหลือ: {item['quantity'] if item else 0})", "error")
            conn.rollback()
            return redirect(url_for('dashboard.room_view', location_name=current_room) if current_room else url_for('dashboard.index'))

        new_qty = item['quantity'] - amount

        # บันทึกประวัติการเบิก
        cursor.execute("INSERT INTO transactions (user_id, status) VALUES (%s, 'อนุมัติแล้ว')", (user_id,))
        transaction_id = cursor.lastrowid
        
        cursor.execute("""
            INSERT INTO transaction_details (transaction_id, item_id, amount) 
            VALUES (%s, %s, %s)
        """, (transaction_id, item_id, amount))

        # ตัดสต็อก
        cursor.execute("UPDATE items SET quantity = %s WHERE item_id = %s", (new_qty, item_id))

        # ส่ง LINE แจ้งเตือนถ้าของใกล้หมด (เหลือน้อยกว่าหรือเท่ากับ 5)
        if new_qty <= 5:
            cursor.execute("SELECT fullname FROM users WHERE user_id = %s", (user_id,))
            user = cursor.fetchone()
            user_name = user['fullname'] if user else "ไม่ระบุ"
            msg = f"⚠️ แจ้งเตือนของใกล้หมด!\n📦 พัสดุ: {item['item_name']}\n📉 คงเหลือเพียง: {new_qty} {item['unit']}\n👤 ผู้เบิกล่าสุด: {user_name}"
            send_line_notify(msg)

        conn.commit()
        flash(f"เบิก {item['item_name']} จำนวน {amount} {item['unit']} เรียบร้อย!", 'success')
    except Exception as e:
        if conn: conn.rollback()
        flash(f'เกิดข้อผิดพลาด: {str(e)}', 'error')
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return redirect(url_for('dashboard.room_view', location_name=current_room) if current_room else url_for('dashboard.index'))

# ======================
# 3. แก้ไขพัสดุ (Update)
# ======================
@inventory_bp.route('/update_item', methods=['POST'])
def update_item():
    conn, cursor = None, None
    current_room = request.form.get('current_room')
    try:
        item_id = request.form['item_id']
        item_name = request.form['item_name']
        storage_id = request.form['storage_id']
        quantity = request.form['quantity']
        unit = request.form['unit']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE items 
            SET item_name=%s, storage_id=%s, quantity=%s, unit=%s 
            WHERE item_id=%s
        """, (item_name, storage_id, quantity, unit, item_id))
        
        conn.commit()
        flash(f'แก้ไขข้อมูล "{item_name}" เรียบร้อย', 'success')
    except Exception as e:
        if conn: conn.rollback()
        flash(f'แก้ไขไม่สำเร็จ: {str(e)}', 'error')
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    
    return redirect(url_for('dashboard.room_view', location_name=current_room) if current_room else url_for('dashboard.index'))

# ======================
# 4. ลบพัสดุ (Delete)
# ======================
@inventory_bp.route('/delete_item/<int:item_id>')
def delete_item(item_id):
    conn, cursor = None, None
    current_room = request.args.get('current_room')
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM items WHERE item_id = %s", (item_id,))
        conn.commit()
        flash('ลบพัสดุเรียบร้อยแล้ว', 'success')
    except Exception as e:
        if conn: conn.rollback()
        # ถ้าลบไม่ได้ มักจะติดประวัติการยืม/เบิก (Foreign Key)
        flash('ไม่สามารถลบได้ (อาจมีประวัติการเบิกหรือยืมของชิ้นนี้อยู่)', 'error')
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
        
    return redirect(url_for('dashboard.room_view', location_name=current_room) if current_room else url_for('dashboard.index'))