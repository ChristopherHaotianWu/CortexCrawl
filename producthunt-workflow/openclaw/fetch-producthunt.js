/**
 * OpenClaw Skill: Product Hunt 产品抓取脚本
 *
 * 此脚本用于从 Product Hunt 抓取符合条件的产品
 * 筛选条件: 投票数 >= 100, 最近 30 天内发布
 *
 * 支持 --full 参数进行全量拉取 (无筛选条件限制)
 *
 * 需要配置 PRODUCT_HUNT_API_TOKEN 环境变量
 */

const axios = require('axios');
const fs = require('fs').promises;
const path = require('path');

// 解析命令行参数
const isFullMode = process.argv.includes('--full');

// 配置
const CONFIG = {
  minVotes: isFullMode ? 0 : 100,
  daysBack: isFullMode ? 365 : 30,
  maxPages: isFullMode ? 50 : 20,
  outputPath: '/data/producthunt/raw_products.json',
  // Product Hunt GraphQL API 端点
  graphqlEndpoint: 'https://www.producthunt.com/frontend/graphql',
  // 获取 API Token 从环境变量
  apiToken: process.env.PRODUCT_HUNT_API_TOKEN || ''
};

/**
 * Product Hunt GraphQL 查询 (增量模式，带 postedAfter)
 */
const POSTS_QUERY = `
  query Posts($first: Int, $after: String, $order: PostsOrder, $postedAfter: DateTime) {
    posts(first: $first, after: $after, order: $order, postedAfter: $postedAfter) {
      edges {
        node {
          id
          name
          tagline
          description
          votesCount
          commentsCount
          createdAt
          url
          website
          thumbnail {
            url
          }
          topics {
            edges {
              node {
                name
              }
            }
          }
          makers {
            id
            name
            username
          }
          user {
            id
            name
            username
          }
        }
        cursor
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
`;

/**
 * Product Hunt GraphQL 查询 (全量模式，不带 postedAfter)
 */
const POSTS_QUERY_FULL = `
  query Posts($first: Int, $after: String, $order: PostsOrder) {
    posts(first: $first, after: $after, order: $order) {
      edges {
        node {
          id
          name
          tagline
          description
          votesCount
          commentsCount
          createdAt
          url
          website
          thumbnail {
            url
          }
          topics {
            edges {
              node {
                name
              }
            }
          }
          makers {
            id
            name
            username
          }
          user {
            id
            name
            username
          }
        }
        cursor
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
`;

/**
 * 计算 N 天前的日期
 */
function getDateDaysAgo(days) {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString();
}

/**
 * 抓取产品数据
 */
async function fetchProducts() {
  const products = [];
  let hasNextPage = true;
  let cursor = null;
  let page = 0;

  const modeLabel = isFullMode ? '全量' : '增量';

  console.log(`🚀 开始抓取 Product Hunt 产品 (${modeLabel}模式)...`);
  if (isFullMode) {
    console.log('📦 全量模式: 无筛选条件限制，最多抓取 50 页');
  } else {
    console.log(`📅 增量模式: 最近 ${CONFIG.daysBack} 天，投票数 >= ${CONFIG.minVotes}`);
  }

  const headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
  };

  // 如果有 API Token，添加到请求头
  if (CONFIG.apiToken) {
    headers['Authorization'] = `Bearer ${CONFIG.apiToken}`;
  }

  while (hasNextPage && page < CONFIG.maxPages) {
    let response;
    let lastError;

    // 构建请求变量
    const variables = {
      first: 50,
      after: cursor,
      order: 'POPULARITY'
    };

    let query;
    if (isFullMode) {
      query = POSTS_QUERY_FULL;
    } else {
      query = POSTS_QUERY;
      variables.postedAfter = getDateDaysAgo(CONFIG.daysBack);
    }

    // 重试逻辑：最多 3 次，指数退避
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        response = await axios.post(
          CONFIG.graphqlEndpoint,
          {
            query: query,
            variables: variables
          },
          {
            headers: headers,
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
      console.error('❌ 达到最大重试次数，终止抓取:', lastError.message);
      if (lastError.response) {
        console.error('响应状态:', lastError.response.status);
      }
      break;
    }

    // 检查 GraphQL 错误
    if (response.data.errors) {
      console.error('❌ GraphQL 错误:', response.data.errors);
      break;
    }

    const data = response.data?.data?.posts;
    if (!data) {
      console.error('❌ API 返回数据格式异常:', response.data);
      break;
    }

    const edges = data.edges || [];

    for (const edge of edges) {
      const product = edge.node;

      // 投票数筛选 (全量模式 minVotes=0，等于跳过)
      const votesCount = product.votesCount || 0;
      if (votesCount < CONFIG.minVotes) {
        continue;
      }

      // 获取话题标签
      const topics = product.topics?.edges?.map(e => e.node.name).join(', ') || '';

      // 获取制作者
      let maker = 'Unknown';
      if (product.makers && product.makers.length > 0) {
        maker = product.makers.map(m => m.name).join(', ');
      } else if (product.user) {
        maker = product.user.name;
      }

      // 格式化产品数据
      const formattedProduct = {
        id: product.id,
        产品名: product.name,
        标语: product.tagline || '',
        产品说明: product.description || product.tagline || '',
        投票数: votesCount,
        评论数: product.commentsCount || 0,
        发布日期: product.createdAt,
        制作者: maker,
        话题标签: topics,
        产品链接: product.url || product.website || `https://www.producthunt.com/posts/${product.id}`,
        产品图片: product.thumbnail?.url || '',
        履历: '',  // 预留字段
        融资历史: '',  // 预留字段
        抓取时间: new Date().toISOString()
      };

      products.push(formattedProduct);
    }

    hasNextPage = data.pageInfo?.hasNextPage || false;
    cursor = data.pageInfo?.endCursor || null;
    page++;

    console.log(`📄 第 ${page} 页抓取完成，当前共 ${products.length} 个产品`);

    // 避免请求过快
    await sleep(1000);
  }

  console.log(`✅ 抓取完成 (${modeLabel}模式)，共 ${products.length} 个产品`);
  return products;
}

/**
 * 保存数据到文件
 */
async function saveProducts(products) {
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
        count: products.length,
        products: products
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
      console.warn('⚠️ 未设置 PRODUCT_HUNT_API_TOKEN，可能遇到访问限制');
    }

    const products = await fetchProducts();
    await saveProducts(products);

    // 输出结果供 OpenClaw 捕获
    console.log(JSON.stringify({
      success: true,
      mode: isFullMode ? 'full' : 'incremental',
      count: products.length,
      file: CONFIG.outputPath
    }));

  } catch (error) {
    console.error('❌ 执行失败:', error.message);
    process.exit(1);
  }
}

// 运行
main();
