import { useEffect, useRef, useState } from 'react'
import { NewClippingForm } from './ClippingPage'

/** The floating Add posting button, on every screen, opening the paste form in an overlay. */
export function AddPosting() {
  const dialog = useRef<HTMLDialogElement>(null)
  // Counts the openings: a fresh key each time, so the form always starts empty
  const [opened, setOpened] = useState(0)

  useEffect(() => {
    // Submitting opens the Clipping, which should not stay under the overlay
    const close = () => dialog.current?.close()
    window.addEventListener('hashchange', close)
    return () => window.removeEventListener('hashchange', close)
  }, [])

  function open() {
    setOpened((n) => n + 1)
    dialog.current?.showModal()
  }

  return (
    <>
      <button type="button" className="fab" onClick={open}>
        <span aria-hidden="true">+</span> Add posting
      </button>
      <dialog
        ref={dialog}
        className="overlay"
        aria-label="Add a job posting"
        // Only a click on the backdrop lands on the dialog itself; its content fills it
        onClick={(event) => event.target === dialog.current && dialog.current.close()}
      >
        <div className="overlay-body">
          <button
            type="button"
            className="overlay-close"
            aria-label="Close"
            onClick={() => dialog.current?.close()}
          >
            ×
          </button>
          {opened > 0 && <NewClippingForm key={opened} />}
        </div>
      </dialog>
    </>
  )
}
