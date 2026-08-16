import React from 'react'
import ReactDOM from 'react-dom/client'
import { KitchenSink } from './components/KitchenSink'
import './styles/global.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <KitchenSink />
  </React.StrictMode>,
)
