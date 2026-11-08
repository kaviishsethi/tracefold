// Examples of public places copies of company material tend to turn up. Tracefold can fetch any approved public URL,
// directly or through Exa/Tavily; these logos are illustrative, not a fixed integration list.
import {
  siAirtable, siAmazons3, siAtlassian, siBitbucket, siCoda, siCodeberg, siCodepen, siDocker, siFigma, siGitbook, siGithub,
  siGitlab, siGooglecloudstorage, siGoogledocs, siGoogledrive, siHuggingface, siInternetarchive, siJsfiddle, siMiro, siNotion,
  siNpm, siPastebin, siPostman, siPypi, siReplit, siTelegram, siTrello,
} from "simple-icons";
import { cx } from "./ui";

const PLATFORMS = [
  { icon: siGithub, name: "GitHub & Gist" },
  { icon: siGitlab, name: "GitLab" },
  { icon: siBitbucket, name: "Bitbucket" },
  { icon: siCodeberg, name: "Codeberg" },
  { icon: siHuggingface, name: "Hugging Face" },
  { icon: siPypi, name: "PyPI" },
  { icon: siNpm, name: "npm" },
  { icon: siDocker, name: "Docker Hub" },
  { icon: siPostman, name: "Postman" },
  { icon: siPastebin, name: "Pastebin" },
  { icon: siNotion, name: "Notion" },
  { icon: siAtlassian, name: "Confluence & Jira" },
  { icon: siGitbook, name: "GitBook" },
  { icon: siCoda, name: "Coda" },
  { icon: siGoogledocs, name: "Google Docs" },
  { icon: siGoogledrive, name: "Google Drive" },
  { icon: siTrello, name: "Trello" },
  { icon: siAirtable, name: "Airtable" },
  { icon: siMiro, name: "Miro" },
  { icon: siFigma, name: "Figma" },
  { icon: siReplit, name: "Replit" },
  { icon: siCodepen, name: "CodePen" },
  { icon: siJsfiddle, name: "JSFiddle" },
  { icon: siAmazons3, name: "Amazon S3" },
  { icon: siGooglecloudstorage, name: "Cloud Storage" },
  { icon: siInternetarchive, name: "Wayback Machine" },
  { icon: siTelegram, name: "Telegram" },
];

export function PlatformLogos({ className }: { className?: string }) {
  return (
    <ul aria-label="Public places Tracefold can check" className={cx("flex flex-wrap items-center justify-center gap-x-[clamp(22px,3vw,40px)] gap-y-6", className)}>
      {PLATFORMS.map(({ icon, name }) => (
        <li key={name} title={name} className="text-[#d9dadd] opacity-70 transition-opacity duration-200 hover:opacity-100">
          <svg viewBox="0 0 24 24" className="size-[28px]" fill="currentColor" role="img" aria-label={name}>
            <path d={icon.path} />
          </svg>
        </li>
      ))}
    </ul>
  );
}
