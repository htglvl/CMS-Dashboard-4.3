declare module "openclaw/plugin-sdk/plugin-entry" {
  export function definePluginEntry(config: any): any;
}

declare module "openclaw/plugin-sdk/tool-plugin" {
  export function defineToolPlugin(config: any): any;
}

declare module "typebox" {
  export const Type: {
    Object: (properties: any, options?: any) => any;
    String: (options?: any) => any;
    Number: (options?: any) => any;
    Boolean: (options?: any) => any;
    Optional: (type: any) => any;
    Union: (types: any[], options?: any) => any;
    Literal: (value: string) => any;
    Array: (items: any) => any;
  };
}
