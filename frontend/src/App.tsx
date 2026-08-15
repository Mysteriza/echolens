import { useState, useRef, useEffect } from 'react'
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
  
  const [question, setQuestion] = useState('')
  const [chatHistory, setChatHistory] = useState<any[]>([])
  
  const [loading, setLoading] = useState(false)
  const [asking, setAsking] = useState(false)
  
  const [activeTab, setActiveTab] = useState<'chat' | 'comments' | 'logs'>('chat')
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [rawComments, setRawComments] = useState<RawComment[]>([])
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
          setActiveTab('chat')
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
        fetchComments(id, 0, false) // Fetch comments when done
        pollLogs(id) // Fetch logs so tab isn't empty
        if (data.status === 'completed') setActiveTab('chat')
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
          <div className="hero-section">
            <div className="hero-text">
              <h1>Understand what consumers actually think.</h1>
              <p>Paste a YouTube URL to extract, analyze, and query hundreds of comments instantly using AI.</p>
            </div>
            <form className="hero-form" onSubmit={handleProcess}>
              <div className="input-wrapper">
                <svg className="search-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22.54 6.42a2.78 2.78 0 0 0-1.94-2C18.88 4 12 4 12 4s-6.88 0-8.6.46a2.78 2.78 0 0 0-1.94 2A29 29 0 0 0 1 11.75a29 29 0 0 0 .46 5.33 2.78 2.78 0 0 0 1.94 2c1.72.46 8.6.46 8.6.46s6.88 0 8.6-.46a2.78 2.78 0 0 0 1.94-2 29 29 0 0 0 .46-5.33 29 29 0 0 0-.46-5.33z"></path><polygon points="9.75 15.02 15.5 11.75 9.75 8.48 9.75 15.02"></polygon></svg>
                <input 
                  type="text" 
                  className="url-input"
                  placeholder="https://www.youtube.com/watch?v=..." 
                  value={url}
                  onChange={e => setUrl(e.target.value)}
                  disabled={loading}
                  autoFocus
                />
                <button type="submit" className="btn-analyze" disabled={!url || loading}>
                  {loading ? 'Starting...' : 'Analyze Video'}
                </button>
              </div>
              
              <div className="limit-selector-custom">
                <span className="limit-label">Analyze Comments:</span>
                <div className="dropdown-container">
                  <div 
                    className="dropdown-trigger" 
                    onClick={() => !loading && setShowDropdown(!showDropdown)}
                    style={{ opacity: loading ? 0.5 : 1, cursor: loading ? 'not-allowed' : 'pointer' }}
                  >
                    {limitOptions.find(o => o.value === limit)?.label}
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
            </form>
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
                <p>Echolens is currently analyzing each comment using AI to extract sentiment, product aspects, and complaints. Once ready, you can ask specific questions about the consumer opinions.</p>
              </div>
            </aside>

            <section className="main-panel">
              <div className="tab-header">
                <button 
                  className={`tab-btn ${activeTab === 'chat' ? 'active' : ''}`}
                  onClick={() => setActiveTab('chat')}
                >
                  AI Chat
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
                {activeTab === 'chat' && (
                  <div className="chat-container">

                    <div className="chat-history">
                      {chatHistory.length === 0 ? (
                        <div className="empty-chat">
                          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--border-strong)" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
                          <h3>Ask about the opinions</h3>
                          <p>Try asking: "What is the main complaint about the battery?" or "Do people think this is worth the price?"</p>
                        </div>
                      ) : (
                        chatHistory.map((msg, idx) => (
                          <div key={idx} className={`message-wrapper ${msg.type}`}>
                            {msg.type === 'question' && (
                              <div className="message user-message">{msg.content}</div>
                            )}
                            
                            {msg.type === 'error' && (
                              <div className="message error-message">{msg.content}</div>
                            )}
                            
                            {msg.type === 'answer' && (
                              <div className="message ai-message">
                                <div className="ai-answer-header">
                                  <span className="ai-label">AI Analysis</span>
                                  <span className={`confidence-pill ${msg.data.confidence?.toLowerCase()}`}>
                                    {msg.data.confidence} Confidence
                                  </span>
                                </div>
                                
                                <p className="ai-text">{msg.data.answer}</p>
                                
                                {msg.data.relevant_aspects?.length > 0 && (
                                  <div className="ai-aspects">
                                    {msg.data.relevant_aspects.map((asp: string, i: number) => (
                                      <span key={i} className="aspect-pill">{asp}</span>
                                    ))}
                                  </div>
                                )}
                                
                                {msg.data.evidence?.length > 0 && (
                                  <div className="evidence-section">
                                    <h5 className="evidence-title">Sources from Comments:</h5>
                                    <div className="evidence-grid">
                                      {msg.data.evidence.map((c: any) => (
                                        <div key={c.id} className="evidence-item">
                                          <div className="evidence-item-header">
                                            <span className="evidence-author">@{c.author}</span>
                                            <span className={`evidence-sentiment ${c.sentiment}`}>{c.sentiment}</span>
                                          </div>
                                          <p className="evidence-quote">"{c.text}"</p>
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
                          <div className="message ai-message loading-message">
                            <span className="loading-dot"></span>
                            <span className="loading-dot"></span>
                            <span className="loading-dot"></span>
                          </div>
                        </div>
                      )}
                      <div ref={chatEndRef} />
                    </div>

                    <div className="chat-input-container">
                      <form className="chat-form" onSubmit={handleAsk}>
                        <input 
                          type="text" 
                          className="chat-input"
                          placeholder={status !== 'completed' ? 'Wait for analysis to complete...' : 'Ask a question about the comments...'} 
                          value={question}
                          onChange={e => setQuestion(e.target.value)}
                          disabled={status !== 'completed' || asking}
                        />
                        <button 
                          type="submit" 
                          className="chat-submit-btn"
                          disabled={status !== 'completed' || asking || !question.trim()}
                        >
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
                        </button>
                      </form>
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
