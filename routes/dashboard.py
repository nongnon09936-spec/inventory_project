from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response, Response
from db import get_db_connection
from datetime import datetime
import csv
from io import StringIO

dashboard_bp = Blueprint('dashboard', __name__)

# ======================
# 1. หน้า Index (ภาพรวม + กราฟ)
# ======================
@dashboard_bp.route('/')
def index():
    conn, cursor = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT SUM(quantity) as total FROM items")
        total_items = cursor.fetchone()['total'] or 0

        cursor.execute("SELECT COUNT(*) as low FROM items WHERE quantity < 10")
        low_stock = cursor.fetchone()['low'] or 0

        cursor.execute("SELECT COUNT(*) as borrowed FROM borrow_transactions WHERE status != 'returned'")
        borrow_count = cursor.fetchone()['borrowed'] or 0

        cursor.execute("""
            SELECT s.location, COUNT(i.item_id) as item_count, COUNT(DISTINCT s.storage_id) as storage_count
            FROM storages s
            LEFT JOIN items i ON s.storage_id = i.storage_id
            GROUP BY s.location
        """)
        room_stats = cursor.fetchall()

        cursor.execute("""
            SELECT s.location, 
                   SUM(CASE WHEN i.item_id IS NOT NULL AND i.quantity < 10 THEN 1 ELSE 0 END) as low_count,
                   SUM(CASE WHEN i.item_id IS NOT NULL AND i.quantity >= 10 THEN 1 ELSE 0 END) as normal_count
            FROM storages s
            LEFT JOIN items i ON s.storage_id = i.storage_id
            GROUP BY s.location
            ORDER BY s.location
        """)
        chart_raw = cursor.fetchall()

        chart_labels = []
        low_stock_data = []
        normal_stock_data = []

        for r in chart_raw:
            if r['location']:
                chart_labels.append(r['location'])
                low_stock_data.append(int(r['low_count'] or 0))
                normal_stock_data.append(int(r['normal_count'] or 0))
        
        cursor.execute("SELECT * FROM users")
        users = cursor.fetchall()
        cursor.execute("SELECT * FROM storages")
        storages = cursor.fetchall()
        locations = list(set([s['location'] for s in storages if s['location']]))

        return render_template('index.html', 
            current_location=None,
            total_items=total_items, low_stock=low_stock, borrow_count=borrow_count,
            room_stats=room_stats, 
            chart_labels=chart_labels, 
            low_stock_data=low_stock_data, 
            normal_stock_data=normal_stock_data,
            users=users, storages=storages, locations=locations
        )
    except Exception as e:
        return f"Database Error: กรุณาตรวจสอบการเชื่อมต่อฐานข้อมูล ({e})"
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# ======================
# 2. หน้าย่อยรายห้อง (Room View)
# ======================
@dashboard_bp.route('/room/<path:location_name>')
def room_view(location_name):
    conn, cursor = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT i.*, s.storage_name, s.location 
            FROM items i 
            JOIN storages s ON i.storage_id = s.storage_id 
            WHERE s.location = %s
        """, (location_name,))
        items = cursor.fetchall()
        
        total_items = sum([i['quantity'] for i in items]) if items else 0
        low_stock = len([i for i in items if i['quantity'] < 10]) if items else 0
        
        cursor.execute("SELECT * FROM users")
        users = cursor.fetchall()
        cursor.execute("SELECT * FROM storages")
        storages = cursor.fetchall()
        locations = list(set([s['location'] for s in storages if s['location']]))
        
        return render_template('index.html', 
            current_location=location_name,
            items=items, total_items=total_items, low_stock=low_stock,
            users=users, storages=storages, locations=locations,
            chart_labels=[], low_stock_data=[], normal_stock_data=[], room_stats=[], borrow_count=0 
        )
    except Exception as e:
        return f"Error Room: {e}"
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# ======================
# 3. ยืมพัสดุ (Borrow)
# ======================
@dashboard_bp.route('/borrow_item', methods=['POST'])
def borrow_item():
    conn, cursor = None, None
    current_room = request.form.get('current_room')
    try:
        item_id = request.form.get('item_id')
        amount = int(request.form.get('amount', 1))
        user_id = request.form.get('user_id')
        note = request.form.get('note', '')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        conn.start_transaction()

        cursor.execute("SELECT quantity, item_name, unit FROM items WHERE item_id = %s FOR UPDATE", (item_id,))
        item = cursor.fetchone()

        if not item or item['quantity'] < amount:
            flash('สต็อกไม่พอให้ยืม', 'error')
            conn.rollback()
            return redirect(url_for('dashboard.room_view', location_name=current_room) if current_room else url_for('dashboard.index'))

        cursor.execute("UPDATE items SET quantity = quantity - %s WHERE item_id = %s", (amount, item_id))
        cursor.execute("""
            INSERT INTO borrow_transactions (item_id, user_id, amount, note, borrow_date, status)
            VALUES (%s, %s, %s, %s, %s, 'borrowed')
        """, (item_id, user_id, amount, note, datetime.now()))

        conn.commit()
        flash(f"ยืม {item['item_name']} สำเร็จ", 'success')
    except Exception as e:
        if conn: conn.rollback()
        flash(f'เกิดข้อผิดพลาด: {e}', 'error')
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return redirect(url_for('dashboard.room_view', location_name=current_room) if current_room else url_for('dashboard.index'))

# ======================
# 4. รับคืนพัสดุ (Return) - แบบชัวร์ๆ ไม่มีพัง!
# ======================
@dashboard_bp.route('/return_item_confirm', methods=['POST'])
def return_item_confirm():
    conn, cursor = None, None
    try:
        # 1. รับ ID จากฟอร์ม (หน้า Tracking ส่งมาในชื่อ 'borrow_id')
        record_id = request.form.get('borrow_id')
        
        # 2. ตรวจสอบจำนวนที่ส่งคืน
        try:
            return_amount = int(request.form.get('return_amount', 0))
        except (ValueError, TypeError):
            flash('จำนวนที่คืนต้องเป็นตัวเลข', 'error')
            return redirect(url_for('dashboard.tracking'))

        if return_amount <= 0:
            flash('จำนวนที่คืนต้องมากกว่า 0', 'error')
            return redirect(url_for('dashboard.tracking'))

        item_condition = request.form.get('item_condition', 'ปกติ')
        return_note = request.form.get('return_note', '')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        conn.start_transaction()

        # 🌟 จุดแก้สำคัญ: เปลี่ยน borrow_id เป็น id ให้ตรงกับ Table ในรูปของคุณ
        cursor.execute("SELECT item_id, amount FROM borrow_transactions WHERE id = %s FOR UPDATE", (record_id,))
        record = cursor.fetchone()

        if not record:
            flash('ไม่พบข้อมูลการยืมนี้', 'error')
            conn.rollback()
            return redirect(url_for('dashboard.tracking'))
            
        if return_amount > record['amount']:
            flash(f"คืนเกินจำนวน! (ยืมไป {record['amount']} ชิ้น)", 'error')
            conn.rollback()
            return redirect(url_for('dashboard.tracking'))

        # 3. คืนสต็อกพัสดุ
        item_id = record['item_id']
        cursor.execute("UPDATE items SET quantity = quantity + %s WHERE item_id = %s", (return_amount, item_id))

        # 4. อัปเดตสถานะการยืม
        remaining = record['amount'] - return_amount
        if remaining <= 0:
            # 🌟 จุดแก้สำคัญ: เปลี่ยน WHERE borrow_id เป็น WHERE id
            cursor.execute("""
                UPDATE borrow_transactions 
                SET status = 'returned', return_date = %s, note = CONCAT(IFNULL(note,''), ' | ', %s)
                WHERE id = %s
            """, (datetime.now(), f"คืนแล้ว ({item_condition}): {return_note}", record_id))
        else:
            # กรณีคืนบางส่วน
            cursor.execute("UPDATE borrow_transactions SET amount = %s WHERE id = %s", (remaining, record_id))

        conn.commit()
        flash('รับคืนพัสดุเรียบร้อย', 'success')
        
    except Exception as e:
        if conn: conn.rollback()
        print(f"Error Return: {e}")
        flash(f'เกิดข้อผิดพลาด: {e}', 'error')
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
        
    return redirect(url_for('dashboard.tracking'))

# ======================
# 5. หน้า Tracking
# ======================
@dashboard_bp.route('/tracking')
def tracking():
    conn, cursor = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT b.*, i.item_name, i.unit, u.fullname, u.department, s.storage_name, s.location
            FROM borrow_transactions b
            JOIN items i ON b.item_id = i.item_id
            JOIN users u ON b.user_id = u.user_id
            JOIN storages s ON i.storage_id = s.storage_id
            WHERE b.status != 'returned'
            ORDER BY b.borrow_date DESC
        """)
        borrowing_list = cursor.fetchall()
        return render_template('tracking.html', borrowing_list=borrowing_list)
    except Exception as e:
        return f"Error: {e}"
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# ======================
# 6. ประวัติการเบิก (History)
# ======================
@dashboard_bp.route('/history')
def history():
    conn, cursor = None, None
    try:
        location = request.args.get('location', '')
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = """
            SELECT t.transaction_date, u.fullname, u.department, 
                   i.item_name, td.amount, i.unit, s.storage_name, s.location, t.status
            FROM transactions t
            JOIN transaction_details td ON t.transaction_id = td.transaction_id
            JOIN items i ON td.item_id = i.item_id
            JOIN users u ON t.user_id = u.user_id
            JOIN storages s ON i.storage_id = s.storage_id
            WHERE 1=1
        """
        params = []
        if location:
            query += " AND s.location = %s"
            params.append(location)
            
        query += " ORDER BY t.transaction_date DESC"
        cursor.execute(query, tuple(params))
        history_data = cursor.fetchall()
        
        return render_template('history.html', history_data=history_data, location=location, start_date=start_date, end_date=end_date)
    except Exception as e:
        flash(f'ไม่สามารถโหลดประวัติได้: {e}', 'error')
        return render_template('history.html', history_data=[])
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# ======================
# 7. ประวัติการยืม-คืน (Borrow History)
# ======================
@dashboard_bp.route('/borrow_history')
def borrow_history():
    conn, cursor = None, None
    try:
        location = request.args.get('location', '')
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = """
            SELECT b.*, i.item_name, i.unit, u.fullname, u.department, s.storage_name, s.location
            FROM borrow_transactions b
            JOIN items i ON b.item_id = i.item_id
            JOIN users u ON b.user_id = u.user_id
            JOIN storages s ON i.storage_id = s.storage_id
            WHERE 1=1
        """
        params = []
        if location:
            query += " AND s.location = %s"
            params.append(location)
            
        query += " ORDER BY b.borrow_date DESC"
        cursor.execute(query, tuple(params))
        history = cursor.fetchall()
        
        return render_template('borrow_history.html', history=history, location=location, start_date=start_date, end_date=end_date)
    except Exception as e:
        flash(f'ไม่สามารถโหลดประวัติได้: {e}', 'error')
        return render_template('borrow_history.html', history=[])
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# ======================
# 8. ส่งออก Excel ของในห้อง (Export Items)
# ======================
@dashboard_bp.route('/export_items')
def export_items():
    # รับค่าแบบเดียวกับประวัติ (History) เป๊ะๆ
    location = request.args.get('location', '') 
    conn, cursor = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # ตรวจสอบเงื่อนไขการกรองห้อง
        if location and location != 'None' and location != '':
            query = """
                SELECT i.item_name, i.quantity, i.unit, s.storage_name, s.location 
                FROM items i 
                JOIN storages s ON i.storage_id = s.storage_id
                WHERE s.location = %s
                ORDER BY i.item_name ASC
            """
            cursor.execute(query, (location,))
            filename = f"inventory_{location}.csv"
        else:
            # ถ้าอยู่หน้าแรก (ไม่มีค่า location) ให้ดึงทั้งหมด
            query = """
                SELECT i.item_name, i.quantity, i.unit, s.storage_name, s.location 
                FROM items i 
                JOIN storages s ON i.storage_id = s.storage_id
                ORDER BY s.location ASC, i.item_name ASC
            """
            cursor.execute(query)
            filename = "inventory_all.csv"
            
        items = cursor.fetchall()
        
        # สร้างไฟล์ CSV
        si = StringIO()
        si.write('\ufeff') # ใส่ BOM เพื่อให้ Excel อ่านภาษาไทยได้
        writer = csv.writer(si)
        writer.writerow(['ชื่อพัสดุ', 'จำนวนคงเหลือ', 'หน่วยนับ', 'ตู้เก็บ', 'ห้อง'])
        
        for item in items:
            writer.writerow([item['item_name'], item['quantity'], item['unit'], item['storage_name'], item['location']])
            
        # ส่งไฟล์ออกไป
        response = make_response(si.getvalue())
        response.headers["Content-Disposition"] = f"attachment; filename={filename}"
        response.headers["Content-type"] = "text/csv; charset=utf-8"
        return response
    except Exception as e:
        print(f"Export Items Error: {e}")
        flash(f"โหลดข้อมูลพัสดุไม่สำเร็จ: {e}", "error")
        return redirect(url_for('dashboard.index'))
    finally:
        # 🌟 ปิดสายฐานข้อมูลเสมอ เพื่อไม่ให้เครื่องค้าง
        if cursor: cursor.close()
        if conn: conn.close()

# ======================
# 9. ส่งออก Excel ประวัติ (Export History)
# ======================
@dashboard_bp.route('/export_history')
def export_history():
    conn, cursor = None, None
    try:
        location = request.args.get('location', '')
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = """
            SELECT t.transaction_date, u.fullname, u.department, 
                   i.item_name, td.amount, i.unit, s.storage_name, s.location, t.status
            FROM transactions t
            JOIN transaction_details td ON t.transaction_id = td.transaction_id
            JOIN items i ON td.item_id = i.item_id
            JOIN users u ON t.user_id = u.user_id
            JOIN storages s ON i.storage_id = s.storage_id
            WHERE 1=1
        """
        params = []
        if location:
            query += " AND s.location = %s"
            params.append(location)
        if start_date:
            query += " AND DATE(t.transaction_date) >= %s"
            params.append(start_date)
        if end_date:
            query += " AND DATE(t.transaction_date) <= %s"
            params.append(end_date)
            
        query += " ORDER BY t.transaction_date DESC"
        cursor.execute(query, tuple(params))
        history_data = cursor.fetchall()
        
        si = StringIO()
        si.write('\ufeff')
        writer = csv.writer(si)
        writer.writerow(['วัน-เวลาที่เบิก', 'ผู้เบิก', 'แผนก', 'รายการ', 'จำนวน', 'หน่วย', 'สถานที่เก็บ', 'สถานะ'])
        
        for row in history_data:
            date_str = row['transaction_date'].strftime('%d/%m/%Y %H:%M') if row['transaction_date'] else ''
            writer.writerow([
                date_str, row['fullname'], row['department'], 
                row['item_name'], row['amount'], row['unit'], 
                f"{row['location']} - {row['storage_name']}", row['status']
            ])
            
        return Response(
            si.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=withdraw_history.csv"}
        )
    except Exception as e:
        flash(f"โหลดประวัติไม่สำเร็จ: {e}", "error")
        return redirect(url_for('dashboard.history'))
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()