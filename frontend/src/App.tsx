import { useState, useRef, useEffect } from 'react'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Legend } from 'recharts'
import './App.css'

interface VideoMetadata {
  title?: string;
  channel?: string;
  thumbnail?: string;
  processed_comments?: number;
}

interface LogEntry {
  message: string;
  level: string;
  created_at: string;
}

interface RawComment {
  id: number;
  author: string;
  text: string;
  likes: number;
  is_spam: boolean;
  sentiment: string;
  confidence: number;
  summary: string;
  is_complaint: boolean;
  is_praise: boolean;
}

function App() {
  const [url, setUrl] = useState('')
  const [limit, setLimit] = useState(99999)
  const [videoId, setVideoId] = useState<number | null>(null)
  const [status, setStatus] = useState<string>('')
  const [videoData, setVideoData] = useState<VideoMetadata>({})
  
  const [geminiEnabled, setGeminiEnabled] = useState(true)
  

  const [loading, setLoading] = useState(false)
  const [asking, setAsking] = useState(false)
  
  const [activeTab, setActiveTab] = useState<'chat' | 'comments' | 'analytics' | 'logs'>('chat')
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [rawComments, setRawComments] = useState<RawComment[]>([])
  const [stats, setStats] = useState<any>(null)
  
  const [question, setQuestion] = useState('')
  const [chatHistory, setChatHistory] = useState<any[]>([])

  useEffect(() => {
    fetch('http://localhost:8000/health')
      .then(res => res.json())
      .then(data => {
        setGeminiEnabled(data.gemini_enabled)
        if (!data.gemini_enabled && activeTab === 'chat') {
          setActiveTab('analytics')
        }
      })
      .catch(e => console.error("Failed to fetch health check", e))
  }, [activeTab])
  

  const [currentPage, setCurrentPage] = useState(1)
  const [commentLimit, setCommentLimit] = useState(15)

  // Modal State
  const [modalConfig, setModalConfig] = useState<{
    isOpen: boolean;
    type: 'reset' | 'stop' | null;
    step: 1 | 2;
  }>({ isOpen: false, type: null, step: 1 });
  
  // Toast State
  const [toast, setToast] = useState<{
    message: string;
    type: 'success' | 'error' | null;
  }>({ message: '', type: null });

  const showToast = (message: string, type: 'success' | 'error') => {
    setToast({ message, type });
    setTimeout(() => {
      setToast({ message: '', type: null });
    }, 3000);
  };

  const chatEndRef = useRef<HTMLDivElement>(null)
  const logsEndRef = useRef<HTMLDivElement>(null)

  const [showDropdown, setShowDropdown] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowDropdown(false)
      }
    }
    
    if (showDropdown) {
      document.addEventListener("mousedown", handleClickOutside)
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside)
    }
  }, [showDropdown])

  const limitOptions = [
    { value: 100, label: '100' },
    { value: 200, label: '200' },
    { value: 300, label: '300' },
    { value: 500, label: '500' },
    { value: 1000, label: '1000' },
    { value: 99999, label: 'All Comments' }
  ]

  const handleProcess = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!url) return
    setLoading(true)
    setShowDropdown(false)
    
    try {
      const res = await fetch('http://localhost:8000/api/videos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, limit })
      })
      const data = await res.json()
      
      if (res.ok) {
        setVideoId(data.video_id)
        setStatus(data.status)
        
        if (data.status === 'completed') {
          setActiveTab('analytics')
          fetchStats(data.video_id)
          fetchComments(data.video_id, 0, false)
          pollLogs(data.video_id) // Fetch logs once so the tab isn't empty
          checkStatus(data.video_id) // Just to get metadata
        } else {
          setActiveTab('logs') // Show logs if it's new and processing
          checkStatus(data.video_id)
          pollLogs(data.video_id)
        }
      } else {
        alert(data.detail || 'Error processing video')
        setLoading(false)
      }
    } catch (e) {
      alert('Failed to connect to API. Please ensure the backend is running.')
      setLoading(false)
    }
  }

  const checkStatus = async (id: number) => {
    try {
      const res = await fetch(`http://localhost:8000/api/videos/${id}`)
      const data = await res.json()
      setStatus(data.status)
      setVideoData({
        title: data.title,
        channel: data.channel,
        thumbnail: data.thumbnail,
        processed_comments: data.processed_comments
      })
      
      if (data.status !== 'completed' && data.status !== 'failed') {
        setTimeout(() => checkStatus(id), 2000)
      } else {
        setLoading(false)
        fetchStats(id)
        setCurrentPage(1)
        fetchComments(id, 1, commentLimit) // Fetch comments when done
        pollLogs(id) // Fetch logs so tab isn't empty
        if (data.status === 'completed') setActiveTab('analytics')
      }
    } catch (e) {
      setLoading(false)
    }
  }

  const pollLogs = async (id: number) => {
    try {
      const res = await fetch(`http://localhost:8000/api/videos/${id}/logs`)
      const data = await res.json()
      setLogs(data)
      
      // Continue polling if not completed or failed
      fetch(`http://localhost:8000/api/videos/${id}`).then(r => r.json()).then(statusData => {
         if (statusData.status !== 'completed' && statusData.status !== 'failed') {
            setTimeout(() => pollLogs(id), 2000)
         }
      })
    } catch (e) {
      console.error("Failed to fetch logs")
    }
  }

  const fetchStats = async (id: number) => {
    try {
      const res = await fetch(`http://localhost:8000/api/videos/${id}/stats`)
      if (res.ok) {
        const data = await res.json()
        setStats(data)
      }
    } catch (e) {
      console.error("Failed to fetch stats")
    }
  }



  const fetchComments = async (id: number, page: number, limit: number) => {
    try {
      const skip = (page - 1) * limit;
      const res = await fetch(`http://localhost:8000/api/videos/${id}/comments?skip=${skip}&limit=${limit}`)
      const data = await res.json()
      setRawComments(data)
    } catch (e) {
      console.error("Failed to fetch comments")
    }
  }

  useEffect(() => {
    if (videoId && status === 'completed') {
      fetchComments(videoId, currentPage, commentLimit)
    }
  }, [currentPage, commentLimit])

  const handleNewAnalysis = () => {
    setVideoId(null)
    setUrl('')
    setStats(null)
    setRawComments([])
    setLogs([])
    setActiveTab('chat')
  }

  const handleResetDatabase = async () => {
    setModalConfig({ isOpen: true, type: 'reset', step: 1 });
  }

  const executeResetDatabase = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/videos/reset-database', { method: 'POST' })
      if (res.ok) {
        showToast("Database reset successfully.", "success")
        setVideoId(null)
        setStatus('')
        setUrl('')
        setVideoData({})
      } else {
        showToast("Failed to reset database.", "error")
      }
    } catch (e) {
      console.error(e)
      showToast("Error connecting to server.", "error")
    }
    setModalConfig({ isOpen: false, type: null, step: 1 });
  }

  const handleStopProcess = async () => {
    setModalConfig({ isOpen: true, type: 'stop', step: 1 });
  }

  const executeStopProcess = async () => {
    if (videoId) {
      try {
        await fetch(`http://localhost:8000/api/videos/${videoId}/cancel`, { method: 'POST' });
      } catch (e) {
        console.error(e);
      }
      setVideoId(null);
      setStatus('');
      setUrl('');
      setVideoData({});
    }
    setModalConfig({ isOpen: false, type: null, step: 1 });
  }


  const handleAsk = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!videoId || !question.trim()) return
    
    const userQ = question
    setQuestion('')
    setAsking(true)
    
    setChatHistory(prev => [...prev, { type: 'question', content: userQ }])
    
    try {
      const res = await fetch(`http://localhost:8000/api/videos/${videoId}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: userQ })
      })
      const data = await res.json()
      setChatHistory(prev => [...prev, { type: 'answer', content: data }])
    } catch (e) {
      setChatHistory(prev => [...prev, { type: 'error', content: 'Failed to retrieve answer from server.' }])
    }
    setAsking(false)
  }

  const handleExportChat = () => {
    if (chatHistory.length === 0) return;
    const exportData = {
      video: videoData,
      export_date: new Date().toISOString(),
      chat_history: chatHistory
    };
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(exportData, null, 2));
    const a = document.createElement('a');
    a.href = dataStr;
    a.download = `echolens-chat-${videoId}-${new Date().getTime()}.json`;
    a.click();
  };

  useEffect(() => {
    if (chatEndRef.current && activeTab === 'chat') {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [chatHistory, asking, activeTab])

  useEffect(() => {
    if (logsEndRef.current && activeTab === 'logs') {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [logs, activeTab])

  const renderStatus = () => {
    if (!status) return null;
    let label = 'Initializing...';
    let dotClass = 'pending';
    
    // Extract total fetched comments from logs to calculate percentage
    let totalFetched = 0;
    if (logs && logs.length > 0) {
      const fetchLog = logs.find(l => l.message && l.message.includes('Successfully fetched'));
      if (fetchLog) {
        const match = fetchLog.message.match(/Successfully fetched (\d+) comments/);
        if (match && match[1]) totalFetched = parseInt(match[1], 10);
      }
    }

    if (status === 'collecting') { 
      label = 'Fetching comments...'; 
      dotClass = 'collecting'; 
    }
    if (status === 'analyzing') { 
      const processed = videoData.processed_comments || 0;
      if (totalFetched > 0) {
        const pct = Math.round((processed / totalFetched) * 100);
        label = `Analyzing AI (${pct}% - ${processed}/${totalFetched} processed)...`;
      } else {
        label = `Analyzing AI (${processed} processed)...`; 
      }
      dotClass = 'analyzing'; 
    }
    if (status === 'completed') { label = `Ready (${videoData.processed_comments || 0} comments)`; dotClass = 'completed'; }
    if (status === 'failed') { label = 'Analysis failed'; dotClass = 'failed'; }
    
    return (
      <div className="status-badge">
        <span className={`status-dot ${dotClass}`}></span>
        {label}
      </div>
    )
  }

  return (
    <div className="app-layout">
      <header className="top-nav">
        <div className="nav-container">
          <div className="logo">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
            <span>Echolens Intelligence</span>
          </div>
        </div>
      </header>

      <main className="main-content">
        {!videoId ? (
          <div className="hero-section">
            <div className="hero-text">
              <h1>Understand what consumers actually think.</h1>
              <p>
                Paste a YouTube URL to extract, analyze, and query hundreds of comments instantly using AI.
              </p>
            </div>
            
            <form onSubmit={handleProcess} className="hero-search-form">
              <div className="hero-search-bar">
                <svg className="search-icon" width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>
                <input 
                  className="hero-search-input"
                  type="text" 
                  placeholder="https://www.youtube.com/watch?v=..." 
                  value={url}
                  onChange={e => setUrl(e.target.value)}
                  disabled={loading}
                  autoFocus
                />
                
                <div className="hero-search-divider"></div>
                
                <div className="dropdown-container" ref={dropdownRef}>
                  <div 
                    className="dropdown-trigger" 
                    onClick={() => !loading && setShowDropdown(!showDropdown)}
                    style={{ opacity: loading ? 0.5 : 1, cursor: loading ? 'not-allowed' : 'pointer' }}
                  >
                    <span>Analyze: {limitOptions.find(o => o.value === limit)?.label}</span>
                    <svg className="dropdown-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
                  </div>
                  
                  {showDropdown && (
                    <ul className="dropdown-menu">
                      {limitOptions.map(opt => (
                        <li 
                          key={opt.value} 
                          onClick={() => { setLimit(opt.value); setShowDropdown(false); }}
                          className={limit === opt.value ? 'selected' : ''}
                        >
                          {opt.label}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <button type="submit" className="hero-search-button" disabled={!url || loading}>
                  {loading ? 'Starting...' : 'Analyze Video'}
                </button>
              </div>
            </form>
            
            <div className="hero-about">
              <h3>How Echolens Works</h3>
              <div className="about-grid">
                <div className="about-card">
                  <div className="about-icon">1</div>
                  <h4>Extract</h4>
                  <p>Fetches comments directly from the YouTube API instantly.</p>
                </div>
                <div className="about-card">
                  <div className="about-icon">2</div>
                  <h4>Analyze</h4>
                  <p>Classifies sentiments and identifies complaints using IndoBERT AI.</p>
                </div>
                <div className="about-card">
                  <div className="about-icon">3</div>
                  <h4>Chat</h4>
                  <p>Query the data and talk to the consumer insights via Gemini AI.</p>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="dashboard">
            <aside className="sidebar">
              <div className="video-card">
                {videoData.thumbnail ? (
                  <img src={videoData.thumbnail} alt="Video thumbnail" className="video-thumb" />
                ) : (
                  <div className="video-thumb-skeleton" />
                )}
                <div className="video-info">
                  <h3 className="video-title" title={videoData.title}>{videoData.title || 'Loading title...'}</h3>
                  <p className="video-channel">{videoData.channel || 'Loading channel...'}</p>
                </div>
                <div className="video-status-container">
                  {renderStatus()}
                </div>
              </div>
              
              <div className="info-panel">
                <h4>How it works</h4>
                <p>Echolens is currently analyzing each comment using AI to extract sentiment and complaints. Once ready, you can ask specific questions about the consumer opinions.</p>
              </div>
              <div className="sidebar-actions">
                {(status === 'collecting' || status === 'analyzing') && (
                  <button className="btn-sidebar-action stop-process" onClick={handleStopProcess} style={{ backgroundColor: '#EF4444', color: 'white', border: 'none' }}>
                    Stop Process
                  </button>
                )}
                <button className="btn-sidebar-action new-analysis" onClick={handleNewAnalysis}>
                  + New Analysis
                </button>
                <button className="btn-sidebar-action reset-db" onClick={handleResetDatabase}>
                  Reset Database
                </button>
              </div>
            </aside>

            <section className="main-panel">
              <div className="tab-header">
                <button 
                  className={`tab-btn ${activeTab === 'analytics' ? 'active' : ''}`}
                  onClick={() => setActiveTab('analytics')}
                >
                  Analytics
                </button>

                <button 
                  className={`tab-btn ${activeTab === 'chat' ? 'active' : ''}`}
                  onClick={() => geminiEnabled && setActiveTab('chat')}
                  style={{ opacity: geminiEnabled ? 1 : 0.5, cursor: geminiEnabled ? 'pointer' : 'not-allowed' }}
                  title={!geminiEnabled ? 'Google AI API key is not configured' : ''}
                >
                  AI Chat {!geminiEnabled && '(Disabled)'}
                </button>
                <button 
                  className={`tab-btn ${activeTab === 'comments' ? 'active' : ''}`}
                  onClick={() => setActiveTab('comments')}
                >
                  Raw Comments
                </button>
                <button 
                  className={`tab-btn ${activeTab === 'logs' ? 'active' : ''}`}
                  onClick={() => setActiveTab('logs')}
                >
                  Terminal Logs
                </button>
              </div>

              <div className="tab-content">
                {activeTab === 'analytics' && stats && (
                  <div className="analytics-container">
                    <div className="stats-header">
                      <h3>Analytics Overview</h3>
                      <p>Sentiment, timeline, and topics for {stats.total_comments} comments.</p>
                    </div>
                    
                    <div className="charts-grid">
                      <div className="chart-card">
                        <h4>Sentiment Distribution</h4>
                        <div className="chart-wrapper">
                          <ResponsiveContainer width="100%" height={250}>
                            <PieChart>
                              <Pie
                                data={stats.sentiment_distribution}
                                cx="50%"
                                cy="50%"
                                innerRadius={60}
                                outerRadius={80}
                                paddingAngle={5}
                                dataKey="value"
                              >
                                {stats.sentiment_distribution.map((entry: any, index: number) => {
                                  const colors: any = { positive: '#10B981', negative: '#EF4444', neutral: '#9CA3AF', mixed: '#F59E0B' }
                                  return <Cell key={`cell-${index}`} fill={colors[entry.name] || '#9CA3AF'} />
                                })}
                              </Pie>
                              <Tooltip />
                              <Legend />
                            </PieChart>
                          </ResponsiveContainer>
                        </div>
                      </div>

                      <div className="chart-card full-width">
                        <h4>Comments Timeline</h4>
                        <div className="chart-wrapper timeline-wrapper">
                          <ResponsiveContainer width="100%" height={250}>
                            <LineChart data={stats.timeline}>
                              <CartesianGrid strokeDasharray="3 3" vertical={false} />
                              <XAxis dataKey="date" />
                              <YAxis />
                              <Tooltip />
                              <Legend />
                              <Line type="monotone" dataKey="positive" stroke="#10B981" strokeWidth={2} />
                              <Line type="monotone" dataKey="negative" stroke="#EF4444" strokeWidth={2} />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                      </div>

                      <div className="chart-card full-width">
                        <h4>Top Frequent Words</h4>
                        <div className="word-cloud">
                          {stats.top_words.map((w: any, i: number) => (
                            <span key={i} className="word-cloud-item" style={{ fontSize: `${Math.max(0.8, Math.min(2, w.value / 10))}rem` }}>
                              {w.text} <span className="word-cloud-count">({w.value})</span>
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {activeTab === 'chat' && geminiEnabled && (
                  <div className="chat-container">
                    {chatHistory.length > 0 && (
                      <div className="chat-actions" style={{ display: 'flex', justifyContent: 'flex-end', paddingBottom: '1rem', borderBottom: '1px solid var(--border-light)', marginBottom: '1rem' }}>
                        <button className="btn-export" onClick={handleExportChat} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem' }}>
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                          Export Chat to JSON
                        </button>
                      </div>
                    )}
                    <div className="chat-history">
                      {chatHistory.length === 0 ? (
                        <div className="empty-chat">
                          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{color: 'var(--text-tertiary)'}}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
                          <h3>Ask Echolens AI</h3>
                          <p>Ask anything about the consumer opinions, complaints, or sentiments from this video.</p>
                        </div>
                      ) : (
                        chatHistory.map((msg, i) => (
                          <div key={i} className={`message-wrapper ${msg.type}`}>
                            {msg.type === 'question' ? (
                              <div className="user-message">{msg.content}</div>
                            ) : (
                              <div className="ai-message">
                                <div className="ai-answer-header">
                                  <span className="ai-label">AI Analysis</span>
                                  <span className={`confidence-pill ${msg.content.confidence.toLowerCase()}`}>
                                    {msg.content.confidence} Confidence
                                  </span>
                                </div>
                                <div className="ai-text">{msg.content.answer}</div>
                                
                                {msg.content.relevant_aspects && msg.content.relevant_aspects.length > 0 && (
                                  <div className="ai-aspects">
                                    {msg.content.relevant_aspects.map((asp: string, j: number) => (
                                      <span key={j} className="aspect-pill">{asp}</span>
                                    ))}
                                  </div>
                                )}
                                
                                {msg.content.evidence && msg.content.evidence.length > 0 && (
                                  <div className="evidence-section">
                                    <div className="evidence-title">Sources from Comments:</div>
                                    <div className="evidence-grid">
                                      {msg.content.evidence.map((ev: any, j: number) => (
                                        <div key={j} className="evidence-item">
                                          <div className="evidence-item-header">
                                            <span className="evidence-author">{ev.author}</span>
                                            <span className={`evidence-sentiment ${ev.sentiment?.toLowerCase() || 'neutral'}`}>
                                              {ev.sentiment?.toUpperCase() || 'NEUTRAL'}
                                            </span>
                                          </div>
                                          <div className="evidence-quote">"{ev.text}"</div>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        ))
                      )}
                      
                      {asking && (
                        <div className="message-wrapper answer">
                          <div className="ai-message">
                            <div className="loading-message">
                              <div className="loading-dot"></div>
                              <div className="loading-dot"></div>
                              <div className="loading-dot"></div>
                              <span style={{marginLeft: '8px', color: 'var(--text-secondary)', fontSize: '0.875rem'}}>AI is analyzing comments...</span>
                            </div>
                          </div>
                        </div>
                      )}
                      <div ref={chatEndRef} />
                    </div>
                    
                    <div className="chat-input-container">
                      <form onSubmit={handleAsk} className="chat-form">
                        <textarea
                          className="chat-input"
                          placeholder="Ask a question about the comments..."
                          value={question}
                          onChange={e => setQuestion(e.target.value)}
                          onKeyDown={e => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                              e.preventDefault()
                              handleAsk(e)
                            }
                          }}
                          rows={2}
                          disabled={asking}
                        />
                        <button type="submit" className="chat-submit-btn" disabled={!question.trim() || asking}>
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
                        </button>
                      </form>
                    </div>
                  </div>
                )}
                
                {activeTab === 'chat' && !geminiEnabled && (
                  <div className="chat-container">
                    <div className="empty-chat" style={{ marginTop: '4rem' }}>
                      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{color: 'var(--text-tertiary)'}}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
                      <h3>AI Chat is Disabled</h3>
                      <p>The Google AI API key has not been configured in the backend environment variables. The overall sentiment analysis continues to function normally.</p>
                    </div>
                  </div>
                )}

                {activeTab === 'comments' && (
                  <div className="comments-container">
                    <div className="comments-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div className="section-title">
                        <h3>Collected Comments ({videoData.processed_comments || rawComments.length})</h3>
                        <p>Raw data and AI structured analysis for each comment.</p>
                      </div>
                      <a 
                        href={`http://localhost:8000/api/videos/${videoId}/export`} 
                        className="btn-export"
                        target="_blank"
                        rel="noreferrer"
                        download
                      >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                        Export CSV
                      </a>
                    </div>
                    {rawComments.length === 0 ? (
                      <div className="empty-state">No comments available yet.</div>
                    ) : (
                      <div className="comments-list">
                        {rawComments.map(c => (
                          <div key={c.id} className="raw-comment-card">
                            <div className="rc-header">
                              <span className="rc-author">@{c.author}</span>
                              <div className="rc-badges">
                                {c.is_spam && <span className="rc-badge spam">Spam Detected</span>}
                                {c.sentiment && <span className={`rc-badge sentiment-${c.sentiment}`}>IndoBERT: {c.sentiment}</span>}
                                {c.confidence !== null && c.confidence !== undefined && <span className="rc-badge confidence">{(c.confidence * 100).toFixed(1)}% Confident</span>}
                                {c.is_complaint && <span className="rc-badge issue">Complaint</span>}
                                {c.is_praise && <span className="rc-badge praise">Praise</span>}
                              </div>
                            </div>
                            <p className="rc-text">{c.text}</p>
                          </div>
                        ))}
                        
                      <div className="pagination-controls">
                        <div className="pagination-left">
                          <label>Items per page:</label>
                          <select 
                            value={commentLimit} 
                            onChange={(e) => {
                              setCommentLimit(Number(e.target.value));
                              setCurrentPage(1);
                            }}
                          >
                            <option value={10}>10</option>
                            <option value={15}>15</option>
                            <option value={30}>30</option>
                            <option value={50}>50</option>
                          </select>
                        </div>
                        <div className="pagination-right">
                          <button 
                            className="btn-pagination"
                            disabled={currentPage === 1}
                            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                          >
                            Previous
                          </button>
                          <span className="pagination-info">
                            Page {currentPage} of {Math.ceil((videoData.processed_comments || 0) / commentLimit) || 1}
                          </span>
                          <button 
                            className="btn-pagination"
                            disabled={currentPage >= Math.ceil((videoData.processed_comments || 0) / commentLimit)}
                            onClick={() => setCurrentPage(p => p + 1)}
                          >
                            Next
                          </button>
                        </div>
                      </div>
                    </div>
                    )}
                  </div>
                )}

                {activeTab === 'logs' && (
                  <div className="terminal-container">
                    <div className="terminal-header">
                      <div className="term-dots"><span></span><span></span><span></span></div>
                      <div className="term-title">system_logs</div>
                    </div>
                    <div className="terminal-body">
                      {logs.map((log, idx) => (
                        <div key={idx} className={`term-line level-${log.level.toLowerCase()}`}>
                          <span className="term-time">[{new Date(log.created_at).toLocaleTimeString()}]</span>
                          <span className="term-msg">{log.message}</span>
                        </div>
                      ))}
                      {status !== 'completed' && status !== 'failed' && (
                        <div className="term-line loading"><span className="term-cursor">_</span></div>
                      )}
                      <div ref={logsEndRef} />
                    </div>
                  </div>
                )}
              </div>
            </section>
          </div>
        )}
      </main>

      {/* Confirmation Modal */}
      {modalConfig.isOpen && (
        <div className="modal-overlay">
          <div className="modal-container">
            <div className="modal-icon-wrapper">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="modal-icon">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                <line x1="12" y1="9" x2="12" y2="13"></line>
                <line x1="12" y1="17" x2="12.01" y2="17"></line>
              </svg>
            </div>
            <h3 className="modal-title">
              {modalConfig.type === 'reset' 
                ? (modalConfig.step === 1 ? 'Reset Database' : 'Final Warning') 
                : 'Stop Process'}
            </h3>
            <p className="modal-message">
              {modalConfig.type === 'reset' && modalConfig.step === 1 && "Are you sure you want to completely reset the database? This will permanently delete ALL videos, comments, and analysis data. This action cannot be undone."}
              {modalConfig.type === 'reset' && modalConfig.step === 2 && "This is your final warning. All data will be irrecoverably lost. Do you wish to proceed?"}
              {modalConfig.type === 'stop' && "Are you sure you want to stop the ongoing analysis? This will cancel the background process and delete the current video's partial data."}
            </p>
            <div className="modal-actions">
              <button 
                className="btn-modal-cancel" 
                onClick={() => setModalConfig({ isOpen: false, type: null, step: 1 })}
              >
                Cancel
              </button>
              <button 
                className="btn-modal-confirm" 
                onClick={() => {
                  if (modalConfig.type === 'reset') {
                    if (modalConfig.step === 1) {
                      setModalConfig(prev => ({ ...prev, step: 2 }));
                    } else {
                      executeResetDatabase();
                    }
                  } else if (modalConfig.type === 'stop') {
                    executeStopProcess();
                  }
                }}
              >
                {modalConfig.type === 'reset' && modalConfig.step === 1 ? 'Yes, Reset Database' : 'Yes, Proceed'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast Notification */}
      {toast.type && (
        <div className={`toast-notification ${toast.type} animate-slide-up`}>
          {toast.type === 'success' ? (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
          ) : (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
          )}
          <span>{toast.message}</span>
        </div>
      )}
    </div>
  )
}

export default App
