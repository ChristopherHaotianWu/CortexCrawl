/**
 * OpenClaw Skill: Kickstarter 项目抓取脚本
 *
 * 此脚本用于从 Kickstarter 抓取符合条件的项目
 * 筛选条件: 2026-01-01 之后发布, 金额 > $500,000
 *
 * 支持 --full 参数进行全量拉取 (无筛选条件限制)
 */

const axios = require('axios');
const fs = require('fs').promises;
const path = require('path');

// 解析命令行参数
const isFullMode = process.argv.includes('--full');

// 配置
const CONFIG = {
  minFunding: isFullMode ? 0 : 500000,
  minLaunchDate: isFullMode ? null : new Date('2026-01-01T00:00:00Z'),
  maxPages: isFullMode ? 50 : 10,
  outputPath: '/data/kickstarter/raw_projects.json',
  // Kickstarter GraphQL API 端点
  graphqlEndpoint: 'https://www.kickstarter.com/graph'
};

/**
 * Kickstarter GraphQL 查询 (增量模式，带 minPledged 筛选)
 */
const DISCOVER_QUERY = `
  query DiscoverProjects($sort: ProjectSort, $first: Int, $after: String) {
    projects(
      sort: $sort
      first: $first
      after: $after
      state: LIVE
      minPledged: 500000
    ) {
      edges {
        node {
          id
          name
          blurb
          pledged {
            currency
            amount
          }
          backersCount
          launchedAt
          deadlineAt
          url
          location {
            displayableName
            country
          }
          category {
            name
          }
          creator {
            name
            id
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
 * Kickstarter GraphQL 查询 (全量模式，无 minPledged 筛选)
 */
const DISCOVER_QUERY_FULL = `
  query DiscoverProjects($sort: ProjectSort, $first: Int, $after: String) {
    projects(
      sort: $sort
      first: $first
      after: $after
      state: LIVE
    ) {
      edges {
        node {
          id
          name
          blurb
          pledged {
            currency
            amount
          }
          backersCount
          launchedAt
          deadlineAt
          url
          location {
            displayableName
            country
          }
          category {
            name
          }
          creator {
            name
            id
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
 * 抓取项目数据
 */
async function fetchProjects() {
  const projects = [];
  let hasNextPage = true;
  let cursor = null;
  let page = 0;

  const query = isFullMode ? DISCOVER_QUERY_FULL : DISCOVER_QUERY;
  const modeLabel = isFullMode ? '全量' : '增量';

  console.log(`🚀 开始抓取 Kickstarter 项目 (${modeLabel}模式)...`);
  if (isFullMode) {
    console.log('📦 全量模式: 无筛选条件限制，最多抓取 50 页');
  }

  while (hasNextPage && page < CONFIG.maxPages) {
    let response;
    let lastError;

    // 重试逻辑：最多 3 次，指数退避
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        response = await axios.post(
          CONFIG.graphqlEndpoint,
          {
            query: query,
            variables: {
              sort: 'NEWEST',
              first: 50,
              after: cursor
            }
          },
          {
            headers: {
              'Content-Type': 'application/json',
              'Accept': 'application/json'
            },
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

    const data = response.data?.data?.projects;
    if (!data) {
      console.error('❌ API 返回数据格式异常:', response.data);
      break;
    }

    const edges = data.edges || [];
    let reachedOldItems = false;

    for (const edge of edges) {
      const project = edge.node;

      // 日期筛选 (全量模式跳过)
      if (CONFIG.minLaunchDate) {
        const launchDate = new Date(project.launchedAt);
        if (launchDate < CONFIG.minLaunchDate) {
          reachedOldItems = true;
          continue;
        }
      }

      // 金额筛选 (全量模式 minFunding=0，等于跳过)
      const amount = project.pledged?.amount || 0;
      if (amount < CONFIG.minFunding) {
        continue;
      }

      // 格式化项目数据
      const formattedProject = {
        id: project.id,
        产品名: project.name,
        国家: project.location?.displayableName || project.location?.country || 'Unknown',
        公司: project.creator?.name || 'Unknown',
        标签: project.category?.name || 'Uncategorized',
        产品说明: project.blurb || '',
        众筹金额_美金: amount,
        众筹人数: project.backersCount || 0,
        众筹开始时间: project.launchedAt,
        创始人: project.creator?.name || 'Unknown',
        项目链接: project.url,
        履历: '',  // 预留字段
        融资历史: '',  // 预留字段
        抓取时间: new Date().toISOString()
      };

      projects.push(formattedProject);
    }

    hasNextPage = data.pageInfo?.hasNextPage || false;
    cursor = data.pageInfo?.endCursor || null;
    page++;

    console.log(`📄 第 ${page} 页抓取完成，当前共 ${projects.length} 个项目`);

    // 增量模式下，已按最新排序，遇到旧项目说明后续页也是旧数据，提前退出
    if (reachedOldItems && !isFullMode) {
      console.log('📅 已到达筛选日期边界，提前退出');
      break;
    }

    // 避免请求过快
    await sleep(1000);
  }

  console.log(`✅ 抓取完成 (${modeLabel}模式)，共 ${projects.length} 个项目`);
  return projects;
}

/**
 * 保存数据到文件
 */
async function saveProjects(projects) {
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
        count: projects.length,
        projects: projects
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
    const projects = await fetchProjects();
    await saveProjects(projects);

    // 输出结果供 OpenClaw 捕获
    console.log(JSON.stringify({
      success: true,
      mode: isFullMode ? 'full' : 'incremental',
      count: projects.length,
      file: CONFIG.outputPath
    }));

  } catch (error) {
    console.error('❌ 执行失败:', error.message);
    process.exit(1);
  }
}

// 运行
main();
