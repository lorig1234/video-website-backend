#!/usr/bin/env python3
"""
Admin CLI Tool for Video Streaming Backend

This tool allows administrators to:
- View all users
- Reset user passwords
- Create new users
- Delete users
- View user statistics

Usage:
    python3 admin_cli.py
"""

import sys
import os
import getpass
from datetime import datetime

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database as db
import auth


def clear_screen():
    """Clear the terminal screen"""
    os.system('clear' if os.name != 'nt' else 'cls')


def print_header():
    """Print CLI header"""
    print("=" * 60)
    print(" 🎬 VIDEO STREAMING - ADMIN CLI")
    print("=" * 60)
    print()


def list_all_users():
    """Display all users with their information"""
    print("\n📋 ALL USERS")
    print("-" * 80)
    
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, username, email, created_at, last_login, is_active 
        FROM users 
        ORDER BY id
    ''')
    users = cursor.fetchall()
    conn.close()
    
    if not users:
        print("No users found.")
        return
    
    print(f"{'ID':<5} {'Username':<20} {'Email':<30} {'Status':<10} {'Created'}")
    print("-" * 80)
    
    for user in users:
        user_id, username, email, created_at, last_login, is_active = user
        status = "✅ Active" if is_active else "❌ Inactive"
        created = created_at.split()[0] if created_at else "N/A"
        print(f"{user_id:<5} {username:<20} {email:<30} {status:<10} {created}")
    
    print(f"\nTotal users: {len(users)}")


def view_user_details(user_id: int = None):
    """View detailed information about a specific user"""
    if user_id is None:
        user_id = input("\nEnter user ID: ").strip()
        if not user_id.isdigit():
            print("❌ Invalid user ID")
            return
        user_id = int(user_id)
    
    # Get user info
    user = db.get_user_by_id(user_id)
    if not user:
        print(f"❌ User with ID {user_id} not found")
        return
    
    print(f"\n👤 USER DETAILS - {user['username']}")
    print("-" * 60)
    print(f"ID:           {user['id']}")
    print(f"Username:     {user['username']}")
    print(f"Email:        {user['email']}")
    print(f"Status:       {'✅ Active' if user['is_active'] else '❌ Inactive'}")
    print(f"Created:      {user.get('created_at', 'N/A')}")
    print(f"Last Login:   {user.get('last_login', 'Never')}")
    
    # Get watch history count
    conn = db.get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM watch_history WHERE user_id = ?', (user_id,))
    watch_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM user_sessions WHERE user_id = ? AND is_valid = 1', (user_id,))
    active_sessions = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(DISTINCT ip_address) FROM user_ips WHERE user_id = ?', (user_id,))
    ip_count = cursor.fetchone()[0]
    
    conn.close()
    
    print(f"\n📊 STATISTICS")
    print(f"Watch History:     {watch_count} episodes")
    print(f"Active Sessions:   {active_sessions}")
    print(f"Known IP Addresses: {ip_count}")


def reset_password():
    """Reset a user's password"""
    print("\n🔑 RESET USER PASSWORD")
    print("-" * 60)
    
    # Show users first
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, username FROM users ORDER BY id')
    users = cursor.fetchall()
    
    print("\nAvailable users:")
    for user_id, username in users:
        print(f"  {user_id}. {username}")
    
    # Get user ID
    user_id = input("\nEnter user ID to reset password: ").strip()
    if not user_id.isdigit():
        print("❌ Invalid user ID")
        conn.close()
        return
    
    user_id = int(user_id)
    
    # Verify user exists
    cursor.execute('SELECT username FROM users WHERE id = ?', (user_id,))
    result = cursor.fetchone()
    
    if not result:
        print(f"❌ User with ID {user_id} not found")
        conn.close()
        return
    
    username = result[0]
    print(f"\n👤 Resetting password for: {username}")
    
    # Get new password
    new_password = getpass.getpass("Enter new password (min 6 chars): ")
    if len(new_password) < 6:
        print("❌ Password must be at least 6 characters")
        conn.close()
        return
    
    confirm_password = getpass.getpass("Confirm new password: ")
    if new_password != confirm_password:
        print("❌ Passwords do not match")
        conn.close()
        return
    
    # Hash and update password
    password_hash = auth.hash_password(new_password)
    
    try:
        cursor.execute(
            'UPDATE users SET password_hash = ? WHERE id = ?',
            (password_hash, user_id)
        )
        conn.commit()
        print(f"✅ Password updated successfully for user: {username}")
        
        # Optionally invalidate all sessions
        invalidate = input("\nInvalidate all active sessions for this user? (y/n): ").lower()
        if invalidate == 'y':
            cursor.execute(
                'UPDATE user_sessions SET is_valid = 0 WHERE user_id = ?',
                (user_id,)
            )
            conn.commit()
            print("✅ All sessions invalidated - user will need to login again")
    
    except Exception as e:
        print(f"❌ Error updating password: {e}")
    finally:
        conn.close()


def create_user():
    """Create a new user"""
    print("\n➕ CREATE NEW USER")
    print("-" * 60)
    
    username = input("Enter username (3-50 chars): ").strip()
    if len(username) < 3:
        print("❌ Username must be at least 3 characters")
        return
    
    email = input("Enter email: ").strip()
    if "@" not in email:
        print("❌ Invalid email address")
        return
    
    password = getpass.getpass("Enter password (min 6 chars): ")
    if len(password) < 6:
        print("❌ Password must be at least 6 characters")
        return
    
    confirm_password = getpass.getpass("Confirm password: ")
    if password != confirm_password:
        print("❌ Passwords do not match")
        return
    
    try:
        user = auth.register_user(username, email, password)
        print(f"\n✅ User created successfully!")
        print(f"ID:       {user['id']}")
        print(f"Username: {user['username']}")
        print(f"Email:    {user['email']}")
    except ValueError as e:
        print(f"❌ Error: {e}")


def toggle_user_status():
    """Activate or deactivate a user"""
    print("\n🔄 TOGGLE USER STATUS")
    print("-" * 60)
    
    user_id = input("Enter user ID: ").strip()
    if not user_id.isdigit():
        print("❌ Invalid user ID")
        return
    
    user_id = int(user_id)
    user = db.get_user_by_id(user_id)
    
    if not user:
        print(f"❌ User with ID {user_id} not found")
        return
    
    current_status = "Active" if user['is_active'] else "Inactive"
    new_status = 0 if user['is_active'] else 1
    new_status_text = "Active" if new_status else "Inactive"
    
    print(f"\nUser: {user['username']}")
    print(f"Current status: {current_status}")
    print(f"New status will be: {new_status_text}")
    
    confirm = input("\nConfirm? (y/n): ").lower()
    if confirm != 'y':
        print("❌ Cancelled")
        return
    
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_active = ? WHERE id = ?', (new_status, user_id))
    conn.commit()
    conn.close()
    
    print(f"✅ User status updated to: {new_status_text}")


def view_statistics():
    """View system statistics"""
    print("\n📊 SYSTEM STATISTICS")
    print("-" * 60)
    
    conn = db.get_db()
    cursor = conn.cursor()
    
    # Total users
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    # Active users
    cursor.execute('SELECT COUNT(*) FROM users WHERE is_active = 1')
    active_users = cursor.fetchone()[0]
    
    # Total watch history entries
    cursor.execute('SELECT COUNT(*) FROM watch_history')
    total_watches = cursor.fetchone()[0]
    
    # Active sessions
    cursor.execute('SELECT COUNT(*) FROM user_sessions WHERE is_valid = 1')
    active_sessions = cursor.fetchone()[0]
    
    # Most active user
    cursor.execute('''
        SELECT u.username, COUNT(*) as watch_count 
        FROM watch_history wh
        JOIN users u ON wh.user_id = u.id
        GROUP BY wh.user_id
        ORDER BY watch_count DESC
        LIMIT 1
    ''')
    most_active = cursor.fetchone()
    
    conn.close()
    
    print(f"Total Users:        {total_users}")
    print(f"Active Users:       {active_users}")
    print(f"Inactive Users:     {total_users - active_users}")
    print(f"Total Watch History: {total_watches} episodes")
    print(f"Active Sessions:    {active_sessions}")
    
    if most_active:
        print(f"Most Active User:   {most_active[0]} ({most_active[1]} episodes watched)")


def main_menu():
    """Display main menu and handle user input"""
    while True:
        print_header()
        print("📋 MAIN MENU")
        print("-" * 60)
        print("1. List all users")
        print("2. View user details")
        print("3. Reset user password")
        print("4. Create new user")
        print("5. Toggle user status (activate/deactivate)")
        print("6. View system statistics")
        print("7. Exit")
        print("-" * 60)
        
        choice = input("\nEnter your choice (1-7): ").strip()
        
        if choice == '1':
            list_all_users()
            input("\nPress Enter to continue...")
            clear_screen()
        
        elif choice == '2':
            view_user_details()
            input("\nPress Enter to continue...")
            clear_screen()
        
        elif choice == '3':
            reset_password()
            input("\nPress Enter to continue...")
            clear_screen()
        
        elif choice == '4':
            create_user()
            input("\nPress Enter to continue...")
            clear_screen()
        
        elif choice == '5':
            toggle_user_status()
            input("\nPress Enter to continue...")
            clear_screen()
        
        elif choice == '6':
            view_statistics()
            input("\nPress Enter to continue...")
            clear_screen()
        
        elif choice == '7':
            print("\n👋 Goodbye!")
            sys.exit(0)
        
        else:
            print("❌ Invalid choice. Please try again.")
            input("\nPress Enter to continue...")
            clear_screen()


if __name__ == "__main__":
    try:
        clear_screen()
        # Initialize database connection
        db.init_db()
        main_menu()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
