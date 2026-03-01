// static/main.js

// 1. 自动记忆功能
const inputIds = ['payer', 'stu_id', 'bank_card', 'warehouse_key'];

document.addEventListener('DOMContentLoaded', () => {
    // 恢复数据
    inputIds.forEach(id => {
        const savedValue = localStorage.getItem(id);
        const el = document.getElementById(id);
        if (savedValue && el) el.value = savedValue;
    });

    // 处理 URL 参数 open
    try {
        const params = new URLSearchParams(window.location.search);
        const open = params.get('open');
        if (open) {
            const listTabBtn = document.getElementById('pills-list-tab');
            if (listTabBtn) listTabBtn.click();
            setTimeout(() => {
                const el = document.getElementById(open);
                if (el) {
                    const bsCollapse = new bootstrap.Collapse(el, {toggle: false});
                    bsCollapse.show();
                    el.scrollIntoView({behavior: 'smooth', block: 'center'});
                }
            }, 250);
        }
    } catch (e) { console.error(e); }

    // --- 新增：操作成功提示自动消失逻辑 ---
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach((alert) => {
        // 3秒后自动关闭
        let timer = setTimeout(() => {
            bootstrap.Alert.getOrCreateInstance(alert).close();
        }, 3000);

        // 鼠标悬停时停止计时，离开后重新计时（防止用户没看清）
        alert.addEventListener('mouseenter', () => clearTimeout(timer));
        alert.addEventListener('mouseleave', () => {
            timer = setTimeout(() => {
                bootstrap.Alert.getOrCreateInstance(alert).close();
            }, 1500);
        });
    });

    // 异步删除附件
    const delForms = Array.from(document.querySelectorAll('form[action^="/delete_attachment/"]'));
    delForms.forEach(form => {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = form.querySelector('button[type="submit"]');
            const fileTag = form.closest('.file-tag');
            btn.disabled = true;
            const original = btn.innerHTML;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

            try {
                const formData = new FormData(form);
                const resp = await fetch(form.action, {
                    method: 'POST',
                    body: formData,
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                });
                const j = await resp.json();
                if (j && j.ok) {
                    if (fileTag) {
                        fileTag.style.transition = 'opacity 0.25s, height 0.25s';
                        fileTag.style.opacity = '0';
                        setTimeout(() => fileTag.remove(), 300);
                    }
                    // 更新状态图标
                    const card = form.closest('.card');
                    const invId = card ? card.dataset.inv : null;
                    const statusEl = invId ? document.getElementById('status-' + invId) : null;
                    if (statusEl) {
                        if (j.has_pay && j.has_order) {
                            statusEl.className = 'status-badge bg-success-subtle text-success border border-success';
                            statusEl.innerHTML = '<i class="bi bi-check-circle-fill me-1"></i>资料齐全';
                        } else {
                            statusEl.className = 'status-badge bg-danger-subtle text-danger border border-danger';
                            statusEl.innerHTML = '<i class="bi bi-exclamation-triangle-fill me-1"></i>缺少附件';
                        }
                    }
                }
            } catch (err) { console.error(err); }
        });
    });

    // 异步删除发票条目
    const delInvLinks = Array.from(document.querySelectorAll('a.delete-invoice'));
    delInvLinks.forEach(link => {
        link.addEventListener('click', async (e) => {
            e.preventDefault();
            if (!confirm('删除后将同时清理本地文件夹，确认吗？')) return;
            const href = link.href;
            const card = link.closest('.card');
            const original = link.innerHTML;
            link.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
            try {
                const resp = await fetch(href, { method: 'GET', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
                const j = await resp.json();
                if (j && j.ok) {
                    if (card) {
                        card.style.transition = 'opacity 0.25s, height 0.25s';
                        card.style.opacity = '0';
                        setTimeout(() => {
                            card.remove();
                            const cnt = document.getElementById('invoices-count');
                            if (cnt) cnt.textContent = Math.max(0, parseInt(cnt.textContent) - 1);
                        }, 300);
                    }
                } else {
                    alert('删除失败');
                    link.innerHTML = original;
                }
            } catch (err) {
                alert('请求失败');
                link.innerHTML = original;
            }
        });
    });

    // 预览按钮逻辑
    document.querySelectorAll('.preview-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const sub = btn.dataset.sub || '';
            const name = btn.dataset.name || '';
            const card = btn.closest('.card');
            const inv = card ? card.dataset.inv : null;
            if (!inv) return;
            const url = '/preview_attachment/' + inv + '?subfolder=' + encodeURIComponent(sub) + '&filename=' + encodeURIComponent(name);
            window.open(url, '_blank');
        });
    });
});

// 上传表单提交记忆
document.getElementById('uploadForm').onsubmit = function() {
    const btn = this.querySelector('button[type="submit"]');
    const fileCount = this.querySelector('input[name="invoice"]').files.length;
    btn.innerHTML = `<span class="spinner-border spinner-border-sm me-2"></span>正在处理 ${fileCount} 个发票...`;
    btn.disabled = true;
    inputIds.forEach(id => {
        localStorage.setItem(id, document.getElementById(id).value);
    });
};

// 上传队列，用于支持多次选择/拖拽文件累积
const uploadQueues = {};

// 文件选择反馈
document.querySelector('input[name="invoice"]').addEventListener('change', function(e) {
    const fileCount = e.target.files.length;
    const titleObj = document.querySelector('#dropZone h6');
    if (fileCount > 0) {
        titleObj.innerHTML = `<i class="bi bi-check-circle-fill text-success"></i> 已准备好 ${fileCount} 个文件`;
    }
});

// 更新附件上传区的文件显示文字
function updateFileName(input, labelId) {
    const label = document.getElementById(labelId);
    const form = input.closest('form');
    const invId = form ? form.dataset.invId : 'global';
    const uploadType = form ? form.dataset.type : '文件';
    const key = `${invId}_${uploadType}`;

    if (!uploadQueues[key]) uploadQueues[key] = [];

    // 将本次选择的文件追加到队列（允许多次选择/拖拽）
    const files = Array.from(input.files || []);
    files.forEach(f => uploadQueues[key].push(f));

    const total = uploadQueues[key].length;
    if (total > 0) {
        label.innerHTML = `<span class="text-primary fw-bold"><i class="bi bi-file-earmark-plus"></i> 已选 ${total} 个文件（可继续添加）</span>`;
    } else {
        label.innerText = "点击或拖拽上传";
    }
}

// 动态加载发票详情
async function loadInvoiceDetail(invId) {
    const loadingDiv = document.getElementById(`detail-loading-${invId}`);
    const contentDiv = document.getElementById(`detail-content-${invId}`);
    
    try {
        const response = await fetch(`/get_invoice_detail/${invId}`);
        const result = await response.json();
        
        if (!result.ok) {
            contentDiv.innerHTML = '<div class="alert alert-danger">加载失败，请确保后端已提供该接口</div>';
            contentDiv.style.display = 'block';
            loadingDiv.style.display = 'none';
            return;
        }
        
        const inv = result.inv;
        const items = result.items;
        const files_list = result.files_list;
        
        // 构建明细表 HTML
        let itemsHtml = '';
        if (items && items.length > 0) {
            itemsHtml = `
                <div class="table-responsive mb-3" style="max-height: 200px; overflow-y: auto;">
                    <table class="table table-sm table-hover align-middle" style="font-size: 0.85rem;">
                        <thead class="table-light sticky-top">
                            <tr class="text-muted">
                                <th>商品名称</th>
                                <th>规格</th>
                                <th class="text-primary">单价(含税)</th>
                                <th>数量</th>
                                <th class="text-end text-primary">金额(含税)</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${items.map(item => `
                                <tr>
                                    <td class="fw-bold text-truncate" style="max-width: 150px;">${item.name}</td>
                                    <td><small class="text-muted">${item.spec || '-'}</small></td>
                                    <td class="text-primary">¥${item.price}</td>
                                    <td>${item.quantity || '-'}</td>
                                    <td class="text-end text-dark fw-bold">¥${item.amount}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            `;
        } else {
            itemsHtml = `
                <div class="row g-3 mb-3">
                    <div class="col-6">
                        <p class="info-label">商品名称</p>
                        <p class="info-value mb-0 text-truncate">${inv.good_name || '未识别'}</p>
                    </div>
                    <div class="col-6">
                        <p class="info-label">规格型号</p>
                        <p class="info-value mb-0 text-muted small">${inv.spec || '-'}</p>
                    </div>
                </div>
            `;
        }
        
        // 构建文件列表 HTML
        let filesHtml = files_list.map(file => `
            <div class="file-tag d-flex align-items-center shadow-sm">
                <i class="bi bi-file-earmark-image text-primary me-2"></i>
                <span class="file-name-text" title="${file.name}">${file.name}</span>
                <div class="btn-group ms-2">
                    <button class="btn btn-sm btn-outline-secondary py-0 px-2 preview-btn" 
                            data-name="${file.name}" 
                            title="预览">
                        <i class="bi bi-eye"></i>
                    </button>
                    ${!file.protected ? `
                    <button class="btn btn-sm btn-outline-warning py-0 px-2 rename-btn" 
                            data-name="${file.name}" 
                            data-inv="${invId}"
                            title="重命名">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger py-0 px-2 delete-btn" 
                            data-name="${file.name}" 
                            title="删除">
                        <i class="bi bi-trash"></i>
                    </button>` : ''}
                </div>
            </div>
        `).join('');
        
        // 构建完整内容 HTML
        const html = `
            <div class="row g-4">
                <div class="col-md-7">
                    <div class="p-3 bg-white rounded-4 border shadow-sm h-100">
                        <h6 class="fw-bold border-bottom pb-2 mb-3">
                            <i class="bi bi-list-ul me-1"></i>发票明细
                        </h6>
                        ${itemsHtml}
                        <div class="row g-3">
                            <div class="col-6">
                                <p class="info-label">发票号码</p>
                                <p class="info-value mb-0" style="font-family: monospace;">${inv.seller}</p>
                            </div>
                            <div class="col-6">
                                <p class="info-label">开票日期</p>
                                <p class="info-value mb-0">${inv.date || '-'}</p>
                            </div>
                            <div class="col-12"><hr class="my-1 text-muted opacity-25"></div>
                            <div class="col-12">
                                <p class="info-label">已包含文件（发票原件及附件）：</p>
                                <div id="files-container-${invId}" class="d-flex flex-wrap gap-2 mt-1">
                                    ${filesHtml}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="col-md-5">
                    <div class="p-3 bg-white rounded-4 border shadow-sm">
                        <h6 class="fw-bold border-bottom pb-2 mb-3">补充截图</h6>
                        <form class="upload-extra-form" data-inv-id="${invId}" data-type="订单" enctype="multipart/form-data">
                            <div class="mb-3">
                                <label class="form-label small fw-bold text-muted">订单截图</label>
                                <div class="attachment-drop-zone">
                                    <i class="bi bi-cart-check text-muted"></i>
                                    <p class="small mb-0 text-muted mt-1" id="label-order-${invId}">点击或拖拽上传</p>
                                    <input type="file" name="files" multiple accept="image/*, application/pdf" onchange="updateFileName(this, 'label-order-${invId}')">
                                </div>
                            </div>
                            <button type="submit" class="btn btn-save btn-sm w-100 py-2">
                                <i class="bi bi-save me-1"></i>上传订单截图
                            </button>
                        </form>
                        
                        <hr class="my-3">
                        
                        <form class="upload-extra-form" data-inv-id="${invId}" data-type="支付" enctype="multipart/form-data">
                            <div class="mb-3">
                                <label class="form-label small fw-bold text-muted">支付截图</label>
                                <div class="attachment-drop-zone">
                                    <i class="bi bi-credit-card-2-back text-muted"></i>
                                    <p class="small mb-0 text-muted mt-1" id="label-pay-${invId}">点击或拖拽上传</p>
                                    <input type="file" name="files" multiple accept="image/*, application/pdf" onchange="updateFileName(this, 'label-pay-${invId}')">
                                </div>
                            </div>
                            <button type="submit" class="btn btn-save btn-sm w-100 py-2">
                                <i class="bi bi-save me-1"></i>上传支付截图
                            </button>
                        </form>
                    </div>
                </div>
            </div>
        `;
        
        contentDiv.innerHTML = html;
        contentDiv.style.display = 'block';
        loadingDiv.style.display = 'none';
        
        // 重新绑定新增的按钮事件
        bindFileActions(invId);
        
        // 重新绑定上传表单（两个表单都需要绑定）
        const forms = contentDiv.querySelectorAll('.upload-extra-form');
        forms.forEach(form => {
            form.removeEventListener('submit', uploadFormHandler);
            form.addEventListener('submit', uploadFormHandler);
        });
    } catch (error) {
        contentDiv.innerHTML = `<div class="alert alert-danger">由于目前是纯净 API 版本，详情加载接口已被暂时移除。</div>`;
        contentDiv.style.display = 'block';
        loadingDiv.style.display = 'none';
    }
}

// 为文件按钮绑定事件（新增的）
function bindFileActions(invId) {
    const filesContainer = document.getElementById(`files-container-${invId}`);
    if (!filesContainer) return;
    
    filesContainer.querySelectorAll('.preview-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const card = btn.closest('.card');
            const inv = card ? card.dataset.inv : invId;
            const name = btn.dataset.name || '';
            const url = '/preview_attachment/' + inv + '?filename=' + encodeURIComponent(name);
            window.open(url, '_blank');
        });
    });
    
    filesContainer.querySelectorAll('.rename-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.preventDefault();
            const oldName = btn.dataset.name || '';
            const inv = btn.dataset.inv || invId;
            
            // 弹出输入框，提示添加"支付"或"订单"关键词
            const newName = prompt(`重命名文件\n原名: ${oldName}\n\n提示：建议文件名中包含"支付"或"订单"以自动分类\n\n新名:`, oldName);
            if (!newName || newName === oldName) return;
            
            const formData = new FormData();
            formData.append('old_name', oldName);
            formData.append('new_name', newName);
            
            try {
                const response = await fetch(`/rename_attachment/${inv}`, {
                    method: 'POST',
                    body: formData
                });
                const result = await response.json();
                
                if (result.ok) {
                    alert('重命名成功！');
                    
                    // 更新文件列表
                    if (result.files_list) {
                        const filesContainer = document.getElementById(`files-container-${inv}`);
                        filesContainer.innerHTML = result.files_list.map(file => `
                            <div class="file-tag d-flex align-items-center shadow-sm">
                                <i class="bi bi-file-earmark-image text-primary me-2"></i>
                                <span class="file-name-text" title="${file.name}">${file.name}</span>
                                <div class="btn-group ms-2">
                                    <button class="btn btn-sm btn-outline-secondary py-0 px-2 preview-btn" data-name="${file.name}" title="预览">
                                        <i class="bi bi-eye"></i>
                                    </button>
                                    ${!file.protected ? `
                                    <button class="btn btn-sm btn-outline-warning py-0 px-2 rename-btn" data-name="${file.name}" data-inv="${inv}" title="重命名">
                                        <i class="bi bi-pencil"></i>
                                    </button>
                                    <button class="btn btn-sm btn-outline-danger py-0 px-2 delete-btn" data-name="${file.name}" title="删除">
                                        <i class="bi bi-trash"></i>
                                    </button>` : ''}
                                </div>
                            </div>
                        `).join('');
                    }
                    
                    // 更新状态徽章
                    const statusBadge = document.getElementById(`status-${inv}`);
                    if (statusBadge) {
                        if (result.has_pay && result.has_order) {
                            statusBadge.className = 'status-badge bg-success-subtle text-success border border-success';
                            statusBadge.innerHTML = '<i class="bi bi-check-circle-fill me-1"></i>资料齐全';
                        } else {
                            statusBadge.className = 'status-badge bg-danger-subtle text-danger border border-danger';
                            statusBadge.innerHTML = '<i class="bi bi-exclamation-triangle-fill me-1"></i>缺少附件';
                        }
                    }
                    
                    bindFileActions(inv);
                } else {
                    alert(`重命名失败: ${result.error}`);
                }
            } catch (error) {
                alert(`重命名出错: ${error.message}`);
            }
        });
    });
    
    filesContainer.querySelectorAll('.delete-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.preventDefault();
            const filename = btn.dataset.name || '';
            const card = btn.closest('.card');
            const inv = card ? card.dataset.inv : invId;
            
            if (!confirm(`确定删除 ${filename} 吗？`)) return;
            
            const formData = new FormData();
            formData.append('filename', filename);
            
            try {
                const response = await fetch(`/delete_attachment/${inv}`, {
                    method: 'POST',
                    body: formData,
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                });
                const result = await response.json();
                
                if (result.ok) {
                    btn.closest('.file-tag').remove();
                } else {
                    alert(`删除失败: ${result.error}`);
                }
            } catch (error) {
                alert(`删除出错: ${error.message}`);
            }
        });
    });
}


// =======================================================
// 🚀 前端边缘计算：极速图片压缩引擎
// =======================================================
async function compressImage(file, maxWidth = 1600, quality = 0.7) {
    // 如果不是图片，或者体积小于 500KB，直接放行不压缩
    if (!file.type.startsWith('image/') || file.size < 500 * 1024) {
        return file; 
    }
    
    return new Promise((resolve) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = (event) => {
            const img = new Image();
            img.src = event.target.result;
            img.onload = () => {
                const canvas = document.createElement('canvas');
                let width = img.width;
                let height = img.height;

                // 等比例缩放，限制最大宽度
                if (width > maxWidth) {
                    height = Math.round((height * maxWidth) / width);
                    width = maxWidth;
                }

                canvas.width = width;
                canvas.height = height;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0, width, height);

                // 压缩为 JPEG 格式
                canvas.toBlob((blob) => {
                    // 强制把后缀改为 .jpg
                    const newName = file.name.replace(/\.[^/.]+$/, "") + ".jpg";
                    const newFile = new File([blob], newName, {
                        type: 'image/jpeg',
                        lastModified: Date.now()
                    });
                    resolve(newFile);
                }, 'image/jpeg', quality);
            };
        };
    });
}

// 上传表单提交处理器
async function uploadFormHandler(e) {
    e.preventDefault();
    const form = e.target;
    const invId = form.dataset.invId; // 这个会从 data-inv-id 自动转换
    const uploadType = form.dataset.type; // "订单" 或 "支付"
    
    const fileInput = form.querySelector('input[type="file"]');
    const queueKey = `${invId}_${uploadType}`;
    let files = (uploadQueues[queueKey] || []);

    // 如果队列为空，但用户直接选择文件（未触发 updateFileName），则回退到 input.files
    if ((!files || files.length === 0) && fileInput && fileInput.files && fileInput.files.length > 0) {
        files = Array.from(fileInput.files);
    }

    if (!files || files.length === 0) {
        alert('请选择文件');
        return;
    }
    
    // ================= 核心修复：锁定按钮并显示 Loading 动画 =================
    const submitBtn = form.querySelector('button[type="submit"]');
    const originalBtnHtml = submitBtn.innerHTML; // 保存原本的按钮文字和图标
    submitBtn.disabled = true; // 禁用按钮，防止多次点击
    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>上传中...';
    // ========================================================================

    // 计算已有截图的最大序号，确保新上传文件序号连续
    const filesContainer = document.getElementById(`files-container-${invId}`);
    let startIndex = 1;
    if (filesContainer) {
        const existing = Array.from(filesContainer.querySelectorAll('.file-name-text')).map(el => (el.textContent || el.innerText || '').trim());
        // 匹配 "订单截图_数字" 或 "支付截图_数字"
        const re = new RegExp(uploadType + '截图_(\\d+)');
        let max = 0;
        existing.forEach(name => {
            const m = name.match(re);
            if (m && m[1]) {
                const n = parseInt(m[1], 10);
                if (!isNaN(n) && n > max) max = n;
            }
        });
        startIndex = max + 1;
    }

    // 创建新的 FormData，自动命名并压缩文件
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
        const originalFile = files[i];
        
        // ⚡️ 核心魔法：在上传前瞬间执行压缩！
        const file = await compressImage(originalFile);

        const idx = startIndex + i;
        const lastDot = file.name.lastIndexOf('.');
        const ext = lastDot >= 0 ? file.name.slice(lastDot) : '';
        const newName = `${uploadType}截图_${idx}${ext}`;
        formData.append('extra_files', file, newName);
    }
    
    try {
        const response = await fetch(`/upload_extra/${invId}`, {
            method: 'POST',
            body: formData
        });
        const result = await response.json();
        
        if (result.ok) {
            const filesContainer = document.getElementById(`files-container-${invId}`);
            if (filesContainer && result.files_list) {
                filesContainer.innerHTML = result.files_list.map(file => `
                    <div class="file-tag d-flex align-items-center shadow-sm">
                        <i class="bi bi-file-earmark-image text-primary me-2"></i>
                        <span class="file-name-text" title="${file.name}">${file.name}</span>
                        <div class="btn-group ms-2">
                            <button class="btn btn-sm btn-outline-secondary py-0 px-2 preview-btn" data-name="${file.name}" title="预览">
                                <i class="bi bi-eye"></i>
                            </button>
                            ${!file.protected ? `
                            <button class="btn btn-sm btn-outline-warning py-0 px-2 rename-btn" data-name="${file.name}" data-inv="${invId}" title="重命名">
                                <i class="bi bi-pencil"></i>
                            </button>
                            <button class="btn btn-sm btn-outline-danger py-0 px-2 delete-btn" data-name="${file.name}" title="删除">
                                <i class="bi bi-trash"></i>
                            </button>` : ''}
                        </div>
                    </div>
                `).join('');
                
                // 更新状态徽章
                const statusBadge = document.getElementById(`status-${invId}`);
                if (statusBadge) {
                    if (result.has_pay && result.has_order) {
                        statusBadge.className = 'status-badge bg-success-subtle text-success border border-success';
                        statusBadge.innerHTML = '<i class="bi bi-check-circle-fill me-1"></i>资料齐全';
                    } else {
                        statusBadge.className = 'status-badge bg-danger-subtle text-danger border border-danger';
                        statusBadge.innerHTML = '<i class="bi bi-exclamation-triangle-fill me-1"></i>缺少附件';
                    }
                }
                
                bindFileActions(invId);
            }
            
            // 清空队列与表单并重置显示
            uploadQueues[queueKey] = [];
            form.reset();
            const labelId = uploadType === '订单' ? `label-order-${invId}` : `label-pay-${invId}`;
            const label = document.getElementById(labelId);
            if (label) label.innerText = '点击或拖拽上传';
        } else {
            alert(`上传失败: ${result.error}`);
        }
    } catch (error) {
        alert(`上传出错: ${error.message}`);
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalBtnHtml;
    }
}

// "详情"按钮点击事件
document.querySelectorAll('.load-detail-btn').forEach(btn => {
    btn.addEventListener('click', function() {
        const invId = this.dataset.inv;
        const contentDiv = document.getElementById(`detail-content-${invId}`);
        
        // 如果已加载过，则不再加载
        if (contentDiv.innerHTML.trim() === '') {
            loadInvoiceDetail(invId);
        }
    });
});