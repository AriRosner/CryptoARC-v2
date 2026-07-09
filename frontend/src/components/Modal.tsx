import React from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { X } from "lucide-react";
import { Button } from "./Button";
import { cn } from "./utils";

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
}

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  description,
  children,
  className
}) => {
  const shouldReduceMotion = useReducedMotion();
  const panelInitial = shouldReduceMotion ? { opacity: 0 } : { opacity: 0, scale: 0.95, y: 20 };
  const panelExit = shouldReduceMotion ? { opacity: 0 } : { opacity: 0, scale: 0.95, y: 20 };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: shouldReduceMotion ? 0.01 : 0.18 }}
            onClick={onClose}
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md"
            aria-hidden="true"
          />
          <div
            className="fixed bottom-0 right-0 top-0 z-50 flex items-center justify-center p-4 pointer-events-none"
            style={{ left: "var(--cryptoarc-sidebar-width, 0px)" }}
          >
            <motion.div
              initial={panelInitial}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={panelExit}
              transition={{ type: "spring", stiffness: 420, damping: 34, duration: shouldReduceMotion ? 0.01 : undefined }}
              role="dialog"
              aria-modal="true"
              aria-labelledby="modal-title"
              aria-describedby={description ? "modal-description" : undefined}
              className={cn(
                "pointer-events-auto w-full max-w-2xl overflow-hidden rounded-2xl border border-white/10 bg-[#10121c] shadow-2xl shadow-black/60",
                className
              )}
            >
              <div className="relative border-b border-white/5 p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 id="modal-title" className="text-xl font-bold text-white">{title}</h3>
                    {description && (
                      <p id="modal-description" className="mt-1 text-sm text-zinc-400">{description}</p>
                    )}
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={onClose}
                    className="h-8 w-8 rounded-full"
                    aria-label={`Close ${title}`}
                  >
                    <X size={18} />
                  </Button>
                </div>
              </div>
              <div className="max-h-[80vh] overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">
                {children}
              </div>
            </motion.div>
          </div>
        </>
      )}
    </AnimatePresence>
  );
};
