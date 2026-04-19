import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { projectApi } from '@/services/apiClient'
import { demoProjects, isDemoMode } from '@/demo/demoData'
import { isElectronRuntime, selectProjectDirectory } from '@/services/desktopClient'
import { useProjectStore } from '@/stores/projectStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { Project } from '@/types/project'

export default function ProjectsPage() {
  const navigate = useNavigate()
  const { projects, setProjects, addProject, removeProject, setCurrentProject, loading, setLoading } = useProjectStore()
  const { removeProjectSessions } = useWorkspaceStore()
  const [showModal, setShowModal] = useState(false)
  const [formData, setFormData] = useState({ name: '', path: '', language: 'python' })
  const canSelectDirectory = isElectronRuntime()
  const demoMode = isDemoMode()

  useEffect(() => {
    loadProjects()
  }, [])

  const loadProjects = async () => {
    if (demoMode) {
      setProjects(demoProjects)
      setLoading(false)
      return
    }

    setLoading(true)
    try {
      const response = await projectApi.list()
      setProjects(response.data)
    } catch (error) {
      console.error('Failed to load projects:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async () => {
    try {
      const response = await projectApi.create(formData)
      addProject(response.data)
      setShowModal(false)
      setFormData({ name: '', path: '', language: 'python' })
    } catch (error) {
      console.error('Failed to create project:', error)
      alert('创建项目失败')
    }
  }

  const handleDelete = async (project: Project) => {
    if (!confirm('确定要删除这个项目吗？')) return
    try {
      await projectApi.delete(project.id)
      removeProject(project.id)
      removeProjectSessions(project.id)
    } catch (error) {
      console.error('Failed to delete project:', error)
    }
  }

  const handleSelectProject = (project: Project) => {
    setCurrentProject(project)
    navigate('/agent')
  }

  const handleSelectDirectory = async () => {
    const selectedPath = await selectProjectDirectory()

    if (!selectedPath) {
      return
    }

    setFormData((current) => ({ ...current, path: selectedPath }))
  }

  return (
    <div className="flex-1 overflow-auto">
      <div className="max-w-4xl mx-auto p-8">
        <div className="flex justify-between items-center mb-8">
          <div>
            <h2 className="text-2xl font-bold text-gray-900">项目管理</h2>
            <p className="text-gray-500 mt-1">选择或创建项目开始使用 Agent</p>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center gap-2"
          >
            <span>+</span>
            <span>新建项目</span>
          </button>
        </div>

        {loading ? (
          <div className="text-center py-12 text-gray-500">加载中...</div>
        ) : projects.length === 0 ? (
          <div className="text-center py-12 bg-white rounded-xl border border-gray-200">
            <div className="text-6xl mb-4">📁</div>
            <h3 className="text-lg font-medium text-gray-900 mb-2">还没有项目</h3>
            <p className="text-gray-500 mb-6">创建你的第一个项目开始使用 Agent</p>
            <button
              onClick={() => setShowModal(true)}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              创建项目
            </button>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {projects.map((project) => (
              <div
                key={project.id}
                className="bg-white p-6 rounded-xl border border-gray-200 hover:shadow-lg hover:border-blue-300 transition-all cursor-pointer group"
                onClick={() => handleSelectProject(project)}
              >
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 group-hover:text-blue-600">
                      {project.name}
                    </h3>
                    <p className="text-sm text-gray-500 mt-1 truncate">{project.path}</p>
                    {project.language && (
                      <span className="inline-block mt-2 px-2 py-1 text-xs bg-blue-50 text-blue-600 rounded">
                        {project.language}
                      </span>
                    )}
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      handleDelete(project)
                    }}
                    className="text-gray-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    删除
                  </button>
                </div>
                <div className="mt-4 text-sm text-blue-600 opacity-0 group-hover:opacity-100 transition-opacity">
                  点击进入 →
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Create Modal */}
        {showModal && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-white rounded-xl p-6 w-full max-w-md shadow-2xl">
              <h3 className="text-lg font-semibold mb-4">创建新项目</h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    项目名称
                  </label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="我的项目"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    项目路径
                  </label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={formData.path}
                      onChange={(e) => setFormData({ ...formData, path: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="/path/to/project"
                    />
                    {canSelectDirectory && (
                      <button
                        type="button"
                        onClick={handleSelectDirectory}
                        className="shrink-0 rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 transition hover:bg-gray-50"
                      >
                        选择目录
                      </button>
                    )}
                  </div>
                  <p className="mt-1 text-xs text-gray-500">Agent 将在此目录下工作</p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    主要语言
                  </label>
                  <select
                    value={formData.language}
                    onChange={(e) => setFormData({ ...formData, language: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="python">Python</option>
                    <option value="javascript">JavaScript</option>
                    <option value="typescript">TypeScript</option>
                    <option value="rust">Rust</option>
                    <option value="go">Go</option>
                    <option value="java">Java</option>
                  </select>
                </div>
              </div>
              <div className="mt-6 flex justify-end gap-3">
                <button
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg"
                >
                  取消
                </button>
                <button
                  onClick={handleCreate}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                  创建
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
