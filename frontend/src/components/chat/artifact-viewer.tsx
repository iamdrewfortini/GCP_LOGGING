import { FileText, Database, BarChart, Code } from 'lucide-react';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';

// Define Artifact Types
export type ArtifactType = 'sql_query' | 'dashboard_config' | 'json_data' | 'markdown_report' | 'code_snippet';

export interface Artifact {
  id: string;
  type: ArtifactType;
  title: string;
  content: string | object;
  createdAt: string;
}

interface ArtifactViewerProps {
  artifact: Artifact;
  onClose?: () => void;
}

export function ArtifactViewer({ artifact }: ArtifactViewerProps) {
  const renderContent = () => {
    switch (artifact.type) {
      case 'sql_query':
        return (
          <div className="bg-slate-950 p-4 rounded-md overflow-x-auto">
            <code className="text-sm font-mono text-green-400">
              {typeof artifact.content === 'string' ? artifact.content : JSON.stringify(artifact.content, null, 2)}
            </code>
          </div>
        );
      
      case 'json_data':
      case 'dashboard_config':
        return (
          <div className="bg-slate-950 p-4 rounded-md overflow-x-auto">
             <pre className="text-xs font-mono text-blue-300">
               {JSON.stringify(artifact.content, null, 2)}
             </pre>
          </div>
        );

      case 'markdown_report':
        return (
          <div className="prose prose-sm dark:prose-invert max-w-none p-2">
            {/* In a real app, use ReactMarkdown here */}
            <pre className="whitespace-pre-wrap font-sans">{String(artifact.content)}</pre>
          </div>
        );
        
      case 'code_snippet':
        return (
             <div className="bg-slate-950 p-4 rounded-md overflow-x-auto">
            <code className="text-sm font-mono text-white">
              {String(artifact.content)}
            </code>
          </div>
        );

      default:
        return <div className="text-muted-foreground">Unsupported artifact type.</div>;
    }
  };

  const getIcon = () => {
      switch(artifact.type) {
          case 'sql_query': return <Database className="w-4 h-4 mr-2" />;
          case 'dashboard_config': return <BarChart className="w-4 h-4 mr-2" />;
          case 'markdown_report': return <FileText className="w-4 h-4 mr-2" />;
          default: return <Code className="w-4 h-4 mr-2" />;
      }
  }

  return (
    <Card className="w-full h-full border-l-4 border-l-primary/50 shadow-sm">
      <CardHeader className="py-3 px-4 bg-muted/20 border-b">
        <div className="flex items-center justify-between">
            <div className="flex items-center font-medium text-sm">
                {getIcon()}
                {artifact.title}
            </div>
            <div className="text-xs text-muted-foreground uppercase tracking-wider">
                {artifact.type.replace('_', ' ')}
            </div>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <ScrollArea className="h-[300px] w-full p-4">
            {renderContent()}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
