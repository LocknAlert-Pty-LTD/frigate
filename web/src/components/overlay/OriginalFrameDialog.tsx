import { baseUrl } from "@/api/baseUrl";
import { cn } from "@/lib/utils";
import { useEffect, useMemo, useState } from "react";
import { isDesktop, isMobile } from "react-device-detect";
import { useTranslation } from "react-i18next";
import { LuExternalLink } from "react-icons/lu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";

type OriginalFrameDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Tracked object the face came from. Without one there is no camera frame. */
  eventId?: string;
  /** The stored face crop, used when no frame can be loaded. */
  cropPath: string;
  title: string;
  description?: string;
};

/**
 * Shows the whole camera frame a face was found in.
 *
 * Enlarging the crop was the wrong answer to "show me the face bigger": the
 * crop is often a few dozen pixels across, so scaling it up produces a bigger
 * blur and no more detail. The information that is actually missing is context
 * -- who it was, what they were doing, where in the scene they stood -- and that
 * only exists in the original frame.
 *
 * `bbox=1` draws the detection box, so the face under discussion can be picked
 * out of a frame that may contain several people. `crop=0` keeps the full frame
 * rather than the region around the object.
 *
 * Sources are tried in descending order of usefulness, because a snapshot only
 * exists when the camera has `snapshots` enabled:
 *
 *   1. the event snapshot, full resolution
 *   2. the event thumbnail, small but still the whole scene
 *   3. the stored face crop, which is always present
 */
export default function OriginalFrameDialog({
  open,
  onOpenChange,
  eventId,
  cropPath,
  title,
  description,
}: OriginalFrameDialogProps) {
  const { t } = useTranslation(["views/faceLibrary", "common"]);

  const sources = useMemo(() => {
    const candidates: { url: string; label: string }[] = [];

    if (eventId) {
      candidates.push({
        url: `${baseUrl}api/events/${eventId}/snapshot.jpg?crop=0&bbox=1&timestamp=0`,
        label: t("details.fullFrame"),
      });
      candidates.push({
        url: `${baseUrl}api/events/${eventId}/thumbnail.jpg`,
        label: t("details.thumbnailOnly"),
      });
    }

    candidates.push({ url: `${baseUrl}${cropPath}`, label: t("details.cropOnly") });
    return candidates;
  }, [eventId, cropPath, t]);

  const [attempt, setAttempt] = useState(0);

  // a new face means starting again from the best source
  useEffect(() => {
    setAttempt(0);
  }, [sources]);

  const current = sources[Math.min(attempt, sources.length - 1)];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={cn(
          "flex w-auto max-w-[95vw] flex-col items-center gap-2",
          isDesktop && "max-h-[92vh]",
          isMobile && "max-h-[88vh]",
        )}
        onClick={(e) => e.stopPropagation()}
      >
        <DialogHeader className="w-full">
          <DialogTitle className="text-base font-normal smart-capitalize">
            {title}
          </DialogTitle>
          <DialogDescription className="flex items-center gap-2 text-xs text-secondary-foreground">
            <span>{description ?? current.label}</span>
            <a
              className="inline-flex items-center gap-1 underline hover:text-primary"
              href={current.url}
              target="_blank"
              rel="noopener noreferrer"
            >
              {t("details.openOriginal")}
              <LuExternalLink className="size-3" />
            </a>
          </DialogDescription>
        </DialogHeader>
        <img
          // Scaled down to fit, never up. This is a full camera frame, so the
          // limit is the viewport; object-contain keeps the aspect ratio so
          // nothing in the scene is distorted.
          className="max-h-[78vh] max-w-full rounded-lg object-contain"
          src={current.url}
          alt={title}
          onError={() => setAttempt((previous) => previous + 1)}
        />
      </DialogContent>
    </Dialog>
  );
}
