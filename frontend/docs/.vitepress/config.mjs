import { defineConfig } from 'vitepress'

export default defineConfig({
  lang:        'zh-CN',
  title:       'Datapulse · 文档',
  description: 'AI 数据生产平台用户文档',
  base:        '/docs/',
  outDir:      '../public/docs',

  themeConfig: {
    logo: '/logo.svg',
    siteTitle: 'Datapulse 文档',

    nav: [
      { text: '使用指南', link: '/guide/overview' },
      { text: '更新日志', link: '/changelog' },
      { text: '常见问题', link: '/faq' },
    ],

    sidebar: [
      {
        text: '入门',
        items: [
          { text: '平台简介',   link: '/guide/overview'  },
          { text: '快速开始',   link: '/guide/quickstart' },
        ],
      },
      {
        text: '核心功能',
        items: [
          { text: '数据集管理', link: '/guide/dataset'         },
          { text: '数据上传',   link: '/guide/upload'          },
          { text: 'Pipeline 流程', link: '/guide/pipeline'     },
          { text: '预标注',     link: '/guide/pre-annotation'  },
          { text: '人工标注',   link: '/guide/annotation'      },
          { text: '冲突检测',   link: '/guide/conflicts'       },
          { text: '导出数据',   link: '/guide/export'          },
        ],
      },
      {
        text: '其他',
        items: [
          { text: '常见问题',   link: '/faq'       },
          { text: '更新日志',   link: '/changelog' },
        ],
      },
    ],

    socialLinks: [],

    footer: {
      message:   'Datapulse 使用文档，仅供内部使用',
      copyright: `© ${new Date().getFullYear()} Datapulse Team`,
    },

    search: { provider: 'local' },

    editLink: {
      pattern: 'https://github.com/your-org/datapulse/edit/main/docs/:path',
      text:    '在 GitHub 上编辑此页',
    },

    lastUpdated: { text: '最后更新于' },

    outline: { label: '本页目录', level: [2, 3] },

    docFooter: { prev: '上一页', next: '下一页' },
  },
})
