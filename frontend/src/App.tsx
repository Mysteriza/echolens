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
  const [limit, setLimit] = useState(300)
  const [videoId, setVideoId] = useState<number | null>(null)
  const [status, setStatus] = useState<string>('')
  const [videoData, setVideoData] = useState<VideoMetadata>({})
  
  const [geminiEnabled, setGeminiEnabled] = useState(true)
  
  useEffect(() => {
    fetch('http://localhost:8000/health')
      .then(res => res.json())
      .then(data => {
        setGeminiEnabled(data.gemini_enabled)
        // If chat was active and gemini is disabled, switch to analytics
        if (!data.gemini_enabled && activeTab === 'chat') {
          setActiveTab('analytics')
        }
      })
      .catch(e => console.error("Failed to fetch health check", e))
  }, [])
  
  const [loading, setLoading] = useState(false)
  const [asking, setAsking] = useState(false)
  
  const [activeTab, setActiveTab] = useState<'chat' | 'comments' | 'analytics' | 'logs'>('chat')
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [rawComments, setRawComments] = useState<RawComment[]>([])
  const [stats, setStats] = useState<any>(null)
  

  const [commentSkip, setCommentSkip] = useState(0)
  const [hasMoreComments, setHasMoreComments] = useState(true)
  const COMMENT_LIMIT = 50
  
  const chatEndRef = useRef<HTMLDivElement>(null)
  const logsEndRef = useRef<HTMLDivElement>(null)

  const [showDropdown, setShowDropdown] = useState(false)

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
        fetchComments(id, 0, false) // Fetch comments when done
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



  const fetchComments = async (id: number, skip = 0, isAppend = false) => {
    try {
      const res = await fetch(`http://localhost:8000/api/videos/${id}/comments?skip=${skip}&limit=${COMMENT_LIMIT}`)
      const data = await res.json()
      
      if (data.length < COMMENT_LIMIT) {
        setHasMoreComments(false)
      } else {
        setHasMoreComments(true)
      }

      if (isAppend) {
        setRawComments(prev => [...prev, ...data])
      } else {
        setRawComments(data)
      }
      setCommentSkip(skip)
    } catch (e) {
      console.error("Failed to fetch comments")
    }
  }

  const handleNewAnalysis = () => {
    setVideoId(null)
    setUrl('')
    setStats(null)
    setRawComments([])
    setLogs([])
    setActiveTab('chat')
  }

  const handleResetDatabase = async () => {
    if (window.confirm("Are you sure you want to delete ALL analyzed data? This action cannot be undone.")) {
      if (window.confirm("FINAL WARNING: All YouTube videos and comments data in the database will be permanently wiped. Proceed?")) {
        try {
          const res = await fetch('http://localhost:8000/api/videos/reset-database', { method: 'POST' })
          if (res.ok) {
            alert("Database has been reset successfully.")
            window.location.reload()
          } else {
            alert("Failed to reset database.")
          }
        } catch (e) {
          alert("Error connecting to server.")
        }
      }
    }
  }

  const handleLoadMore = () => {
    if (videoId) {
      fetchComments(videoId, commentSkip + COMMENT_LIMIT, true)
    }
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
      setChatHistory(prev => [...prev, { type: 'answer', data }])
    } catch (e) {
      setChatHistory(prev => [...prev, { type: 'error', content: 'Failed to retrieve answer from server.' }])
    }
    setAsking(false)
  }

  useEffect(() => {
    if (chatEndRef.current && activeTab === 'chat') {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [chatHistory, asking, activeTab])

  useEffect(() => {
    if (logsEndRef.current && activeTab === 'logs') {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs, activeTab])

  const renderStatus = () => {
    if (!status) return null;
    let label = 'Initializing...';
    let dotClass = 'pending';
    
    if (status === 'collecting') { label = 'Fetching comments...'; dotClass = 'collecting'; }
    if (status === 'analyzing') { label = `Analyzing AI (${videoData.processed_comments || 0} processed)...`; dotClass = 'analyzing'; }
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
          <div className="hero">
            <h1>Understand what consumers actually think.</h1>
            <p className="subtitle">
              Paste a YouTube URL to extract, analyze, and query hundreds of comments instantly using AI.
            </p>
            
            <form onSubmit={handleProcess} className="hero-form">
              <div className="input-row">
                <div className="input-wrapper">
                  <svg className="youtube-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>
                  <input 
                    type="text" 
                    placeholder="https://www.youtube.com/watch?v=..." 
                    value={url}
                    onChange={e => setUrl(e.target.value)}
                    disabled={loading}
                    autoFocus
                  />
                </div>
                
                <div className="limit-selector-custom" style={{ width: '200px' }}>
                  <div className="dropdown-container">
                    <div 
                      className="dropdown-trigger" 
                      onClick={() => !loading && setShowDropdown(!showDropdown)}
                      style={{ opacity: loading ? 0.5 : 1, cursor: loading ? 'not-allowed' : 'pointer', height: '100%', border: 'none', borderLeft: '1px solid #E5E7EB', borderRadius: '0 50px 50px 0', backgroundColor: '#F9FAFB' }}
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
                </div>
              </div>
              
              <button type="submit" className="btn-analyze-large" disabled={!url || loading}>
                {loading ? 'Starting...' : 'Analyze Video'}
              </button>
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
                                
                                {msg.content.supporting_evidence && msg.content.supporting_evidence.length > 0 && (
                                  <div className="evidence-section">
                                    <div className="evidence-title">Sources from Comments:</div>
                                    <div className="evidence-grid">
                                      {msg.content.supporting_evidence.map((ev: any, j: number) => (
                                        <div key={j} className="evidence-item">
                                          <div className="evidence-item-header">
                                            <span className="evidence-author">{ev.author}</span>
                                            <span className={`evidence-sentiment ${ev.sentiment.toLowerCase()}`}>
                                              {ev.sentiment}
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
                      <div>
                        <h3>Collected Comments ({rawComments.length})</h3>
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
                        
                        {hasMoreComments && (
                          <button className="btn-load-more" onClick={handleLoadMore}>
                            Load More Comments
                          </button>
                        )}
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
    </div>
  )
}

export default App
