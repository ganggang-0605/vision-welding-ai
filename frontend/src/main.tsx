import { IconContext } from '@phosphor-icons/react'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router/dom'
import './index.css'
import { router } from './router'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {/* 아이콘은 Phosphor 한 종류만 쓴다. 굵기·크기 기본값을 여기서 한 번 정한다. */}
    <IconContext.Provider value={{ size: 18, weight: 'regular', mirrored: false }}>
      <RouterProvider router={router} />
    </IconContext.Provider>
  </StrictMode>,
)
