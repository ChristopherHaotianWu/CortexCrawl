/**
 * OpenClaw Skill: 微信小程序抓取脚本
 *
 * 此脚本用于从阿拉丁指数 (aldzs.com) 抓取热门微信小程序数据
 * 筛选条件: 月活跃用户 >= 10000
 *
 * 支持 --full 参数进行全量拉取 (无筛选条件限制)
 *
 * 需要配置 ALADING_API_TOKEN 环境变量
 */

const axios = require('axios');
const fs = require('fs').promises;
const path = require('path');

// 解析命令行参数
const isFullMode = process.argv.includes('--full');

// 配置
const CONFIG = {
  minMonthlyActiveUsers: isFullMode ? 0 : 10000,
  maxPages: isFullMode ? 50 : 20,
  outputPath: '/data/wechat-miniprogram/raw_miniprograms.json',
  // 阿拉丁指数 API 端点
  apiBaseUrl: 'https://www.aldzs.com/api',
  // 获取 API Token 从环境变量
  apiToken: process.env.ALADING_API_TOKEN || ''
};

/**
 * 支持的小程序分类列表
 * 来源: 阿拉丁指数分类体系
 */
const CATEGORIES = [
  'all',          // 综合排行
  'shopping',     // 购物
  'tools',        // 工具
  'life',         // 生活服务
  'food',         // 美食
  'travel',       // 旅游
  'finance',      // 金融
  'education',    // 教育
  'entertainment', // 娱乐
  'social',       // 社交
  'health',       // 健康
  'news'          // 资讯
];

/**
 * 获取请求头
 */
function getHeaders() {
  const headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'User-Agent': 'Mozilla/5.0 (compatible; CortexCrawl/1.0)'
  };
  if (CONFIG.apiToken) {
    headers['Authorization'] = `Bearer ${CONFIG.apiToken}`;
  }
  return headers;
}

/**
 * 抓取指定分类的排行榜数据
 */
async function fetchCategoryRank(category, page) {
  let response;
  let lastError;

  // 重试逻辑：最多 3 次，指数退避
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      response = await axios.get(
        `${CONFIG.apiBaseUrl}/rank/applets`,
        {
          params: {
            category: category,
            page: page,
            pageSize: 50,
            sortBy: 'monthlyActiveUsers',
            order: 'desc'
          },
          headers: getHeaders(),
          timeout: 30000
        }
      );
      lastError = null;
      break;
    } catch (error) {
      lastError = error;
      if (attempt < 2) {
        const wait = Math.pow(2, attempt) * 1000;
        console.warn(`⚠️ 请求失败，${wait / 1000}s 后重试 (${attempt + 1}/3): ${error.message}`);
        await sleep(wait);
      }
    }
  }

  if (lastError) {
    console.error(`❌ 分类 "${category}" 第 ${page} 页请求失败:`, lastError.message);
    if (lastError.response) {
      console.error('响应状态:', lastError.response.status);
    }
    return null;
  }

  return response.data;
}

/**
 * 格式化小程序数据
 */
function formatMiniProgram(item, category) {
  const monthlyActiveUsers = item.monthlyActiveUsers || item.mau || 0;
  const dailyActiveUsers = item.dailyActiveUsers || item.dau || 0;

  return {
    id: item.id || item.appId || '',
    小程序名称: item.name || item.appName || '',
    分类: item.category || category || '',
    简介: item.description || item.desc || '',
    开发者: item.developer || item.company || item.owner || '',
    月活用户数: monthlyActiveUsers,
    日均活跃用户: dailyActiveUsers,
    评分: item.rating || item.score || 0,
    上线日期: item.releaseDate || item.createTime || '',
    小程序ID: item.appId || item.id || '',
    封面图: item.coverUrl || item.icon || '',
    标签: Array.isArray(item.tags) ? item.tags.join(', ') : (item.tags || ''),
    小程序链接: item.appId ? `https://weixin.qq.com/r/${item.appId}` : '',
    履历: '',  // 预留字段
    融资历史: '',  // 预留字段
    抓取时间: new Date().toISOString()
  };
}

/**
 * 抓取所有小程序数据
 */
async function fetchMiniPrograms() {
  const miniPrograms = [];
  const seenIds = new Set();
  const modeLabel = isFullMode ? '全量' : '增量';

  console.log(`🚀 开始抓取微信小程序数据 (${modeLabel}模式)...`);
  if (isFullMode) {
    console.log('📦 全量模式: 无筛选条件限制，最多抓取 50 页/分类');
  } else {
    console.log(`📊 增量模式: 月活用户 >= ${CONFIG.minMonthlyActiveUsers.toLocaleString()}`);
  }

  // 只抓取综合排行榜 (all)，避免重复数据
  const categoriesToFetch = ['all'];

  for (const category of categoriesToFetch) {
    let page = 1;
    let hasMore = true;

    console.log(`\n📂 抓取分类: ${category}`);

    while (hasMore && page <= CONFIG.maxPages) {
      const data = await fetchCategoryRank(category, page);

      if (!data) {
        console.error(`❌ 分类 "${category}" 第 ${page} 页获取失败，跳过`);
        break;
      }

      // 兼容不同 API 响应格式
      const items = data.data || data.list || data.items || data.records || [];
      const totalPages = data.totalPages || data.total_pages || data.pages || 1;

      if (!Array.isArray(items) || items.length === 0) {
        console.log(`📭 分类 "${category}" 第 ${page} 页无数据，停止`);
        break;
      }

      let reachedThreshold = false;

      for (const item of items) {
        const mau = item.monthlyActiveUsers || item.mau || 0;

        // 月活筛选 (全量模式跳过)
        if (mau < CONFIG.minMonthlyActiveUsers) {
          reachedThreshold = true;
          continue;
        }

        const appId = item.appId || item.id || '';

        // 去重
        if (appId && seenIds.has(appId)) {
          continue;
        }
        if (appId) {
          seenIds.add(appId);
        }

        miniPrograms.push(formatMiniProgram(item, category));
      }

      console.log(`  📄 第 ${page} 页完成，当前共 ${miniPrograms.length} 个小程序`);

      hasMore = page < totalPages;
      page++;

      // 增量模式下，已按月活降序排列，遇到低于阈值的停止继续抓取
      if (reachedThreshold && !isFullMode) {
        console.log(`  📉 已到达月活阈值，提前退出分类 "${category}"`);
        break;
      }

      // 避免请求过快
      await sleep(1000);
    }
  }

  console.log(`\n✅ 抓取完成 (${modeLabel}模式)，共 ${miniPrograms.length} 个小程序`);
  return miniPrograms;
}

/**
 * 保存数据到文件
 */
async function saveMiniPrograms(miniPrograms) {
  try {
    // 确保目录存在
    const dir = path.dirname(CONFIG.outputPath);
    await fs.mkdir(dir, { recursive: true });

    // 保存为 JSON
    await fs.writeFile(
      CONFIG.outputPath,
      JSON.stringify({
        timestamp: new Date().toISOString(),
        mode: isFullMode ? 'full' : 'incremental',
        count: miniPrograms.length,
        miniprograms: miniPrograms
      }, null, 2)
    );

    console.log(`💾 数据已保存到: ${CONFIG.outputPath}`);
  } catch (error) {
    console.error('❌ 保存数据失败:', error.message);
    throw error;
  }
}

/**
 * 休眠函数
 */
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * 主函数
 */
async function main() {
  try {
    if (!CONFIG.apiToken) {
      console.warn('⚠️ 未设置 ALADING_API_TOKEN 环境变量，可能遇到访问限制。请在 .env 文件中配置或从 https://www.aldzs.com/developer 获取');
    }

    const miniPrograms = await fetchMiniPrograms();
    await saveMiniPrograms(miniPrograms);

    // 输出结果供 OpenClaw 捕获
    console.log(JSON.stringify({
      success: true,
      mode: isFullMode ? 'full' : 'incremental',
      count: miniPrograms.length,
      file: CONFIG.outputPath
    }));

  } catch (error) {
    console.error('❌ 执行失败:', error.message);
    process.exit(1);
  }
}

// 运行
main();
