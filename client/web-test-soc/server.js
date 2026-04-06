const express = require('express');
const bodyParser = require('body-parser');
const app = express();

app.use(bodyParser.urlencoded({ extended: true }));

// 🚨 TRẠM GÁC TOÀN CỤC (GLOBAL MIDDLEWARE) 🚨
app.use((req, res, next) => {
    const clientIp = req.headers['x-forwarded-for'] || req.socket.remoteAddress;
    const timestamp = new Date().toISOString();
    const userAgent = req.headers['user-agent'] || 'Unknown Tool';

    console.log(`{"timestamp": "${timestamp}", "action": "http_request", "ip": "${clientIp}", "method": "${req.method}", "path": "${req.originalUrl}", "user_agent": "${userAgent}"}`);
    next();
});

// Giao diện trang chủ
app.get('/', (req, res) => {
    res.send(`
        <h2>Hệ thống Test SOC - Client Web</h2>
        <form action="/login" method="POST">
            Username: <input type="text" name="username"><br><br>
            Password: <input type="password" name="password"><br><br>
            <button type="submit">Login</button>
        </form>
    `);
});

// Xử lý Login (Đã vá lỗi Crash bằng || {})
app.post('/login', (req, res) => {
    const { username, password } = req.body || {};
    const clientIp = req.headers['x-forwarded-for'] || req.socket.remoteAddress;
    const timestamp = new Date().toISOString();

    if (username === 'admin' && password === '123456') {
        console.log(`{"timestamp": "${timestamp}", "action": "login_success", "ip": "${clientIp}", "username": "${username}"}`);
        res.send('<h3>Đăng nhập thành công!</h3><a href="/">Quay lại</a>');
    } else {
        console.log(`{"timestamp": "${timestamp}", "action": "login_failed", "ip": "${clientIp}", "username": "${username}", "password_tried": "${password}"}`);
        res.status(401).send('<h3>Sai tài khoản hoặc mật khẩu!</h3><a href="/">Thử lại</a>');
    }
});

// Lắng nghe cổng 80 (cần quyền sudo khi chạy)
app.listen(80, () => {
    console.log('Client Web đang chạy ở cổng 80...');
});