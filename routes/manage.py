from flask import Blueprint, request, redirect, url_for, flash
from db import get_db_connection

manage_bp = Blueprint('manage', __name__)

def redirect_back(default='dashboard.index'):
    current_room = request.form.get('current_room') or request.args.get('current_room')
    if current_room and current_room != 'None' and current_room != '':
        return redirect(url_for('dashboard.room_view', location_name=current_room))
    return redirect(url_for(default))

# ==================== 1. จัดการผู้ใช้งาน ====================
@manage_bp.route('/add_user', methods=['POST'])
def add_user():
    conn, cursor = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (fullname, department) VALUES (%s, %s)", 
                       (request.form['fullname'], request.form['department']))
        conn.commit()
        flash('บันทึกรายชื่อผู้ใช้ใหม่เรียบร้อยแล้ว', 'success')
    except Exception as e:
        if conn: conn.rollback()
        flash(f'เกิดข้อผิดพลาด: {str(e)}', 'error')
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return redirect_back()

@manage_bp.route('/update_user', methods=['POST'])
def update_user():
    conn, cursor = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET fullname=%s, department=%s WHERE user_id=%s", 
                       (request.form['fullname'], request.form['department'], request.form['user_id']))
        conn.commit()
        flash('แก้ไขข้อมูลผู้ใช้สำเร็จ', 'success')
    except Exception as e:
        if conn: conn.rollback()
        flash(f'แก้ไขไม่สำเร็จ: {str(e)}', 'error')
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return redirect_back()

@manage_bp.route('/delete_user/<int:user_id>')
def delete_user(user_id):
    conn, cursor = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        conn.commit()
        flash('ลบรายชื่อผู้ใช้เรียบร้อยแล้ว', 'success')
    except Exception as e:
        if conn: conn.rollback()
        flash('ไม่สามารถลบได้ (อาจมีประวัติการเบิกหรือยืมของค้างอยู่)', 'error')
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return redirect_back()

# ==================== 2. จัดการตู้/ชั้นวางเก็บของ ====================
@manage_bp.route('/add_storage', methods=['POST'])
def add_storage():
    conn, cursor = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO storages (storage_name, location) VALUES (%s, %s)", 
                       (request.form['storage_name'], request.form['location']))
        conn.commit()
        flash('เพิ่มตู้เก็บของใหม่สำเร็จ', 'success')
    except Exception as e:
        if conn: conn.rollback()
        flash(f'เกิดข้อผิดพลาด: {str(e)}', 'error')
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return redirect_back()

@manage_bp.route('/update_storage', methods=['POST'])
def update_storage():
    conn, cursor = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE storages SET storage_name=%s, location=%s WHERE storage_id=%s", 
                       (request.form['storage_name'], request.form['location'], request.form['storage_id']))
        conn.commit()
        flash('แก้ไขข้อมูลตู้เก็บของสำเร็จ', 'success')
    except Exception as e:
        if conn: conn.rollback()
        flash(f'แก้ไขไม่สำเร็จ: {str(e)}', 'error')
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return redirect_back()

@manage_bp.route('/delete_storage/<int:storage_id>')
def delete_storage(storage_id):
    conn, cursor = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM storages WHERE storage_id = %s", (storage_id,))
        conn.commit()
        flash('ลบตู้เก็บของเรียบร้อยแล้ว', 'success')
    except Exception as e:
        if conn: conn.rollback()
        flash('ไม่สามารถลบได้ (ยังมีของอยู่ในตู้นี้ หรือมีประวัติการเบิก)', 'error')
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return redirect_back()

# ==================== 3. จัดการห้อง/สถานที่ ====================

# 🌟 เพิ่มฟังก์ชันแก้ไขชื่อห้องที่หายไป
@manage_bp.route('/edit_room', methods=['POST'])
def edit_room():
    conn, cursor = None, None
    try:
        old_name = request.form.get('old_name')
        new_name = request.form.get('new_name')
        
        if not old_name or not new_name:
            flash('ข้อมูลชื่อห้องไม่ถูกต้อง', 'error')
            return redirect(url_for('dashboard.index'))
            
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # แก้ไขชื่อห้องโดยการเปลี่ยนค่า location ในตาราง storages
        cursor.execute("UPDATE storages SET location = %s WHERE location = %s", (new_name, old_name))
        conn.commit()
        flash(f'เปลี่ยนชื่อห้องจาก "{old_name}" เป็น "{new_name}" เรียบร้อยแล้ว', 'success')
        
        # กลับไปหน้าห้องชื่อใหม่
        return redirect(url_for('dashboard.room_view', location_name=new_name))
    except Exception as e:
        if conn: conn.rollback()
        flash(f'แก้ไขชื่อห้องไม่สำเร็จ: {str(e)}', 'error')
        return redirect(url_for('dashboard.index'))
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

@manage_bp.route('/delete_room/<location_name>')
def delete_room(location_name):
    conn, cursor = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        conn.start_transaction()
        
        cursor.execute("""
            DELETE FROM borrow_transactions 
            WHERE item_id IN (SELECT item_id FROM items WHERE storage_id IN (SELECT storage_id FROM storages WHERE location = %s))
        """, (location_name,))

        cursor.execute("""
            DELETE FROM transaction_details 
            WHERE item_id IN (SELECT item_id FROM items WHERE storage_id IN (SELECT storage_id FROM storages WHERE location = %s))
        """, (location_name,))

        cursor.execute("""
            DELETE FROM items 
            WHERE storage_id IN (SELECT storage_id FROM storages WHERE location = %s)
        """, (location_name,))
        
        cursor.execute("DELETE FROM storages WHERE location = %s", (location_name,))
        
        conn.commit()
        flash(f'ลบห้อง "{location_name}" พร้อมพัสดุและประวัติทั้งหมดเรียบร้อยแล้ว', 'success')

    except Exception as e:
        if conn: conn.rollback()
        flash(f'เกิดข้อผิดพลาด ไม่สามารถลบได้: {str(e)}', 'error')
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return redirect(url_for('dashboard.index'))