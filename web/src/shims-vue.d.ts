declare module '*.vue' {
  import { DefineComponent } from 'vue'
  const component: DefineComponent
  export default component
}

declare module '*.svg' {
  const content: string;
  export default content;
}

declare module '*.svg?url' {
  const content: string;
  export default content;
}

declare module '@vue-office/docx' {
  import { DefineComponent } from 'vue';
  const VueOfficeDocx: DefineComponent<{}, {}, any>;
  export default VueOfficeDocx;
}

declare module '@vue-office/excel' {
  import { DefineComponent } from 'vue';
  const VueOfficeExcel: DefineComponent<{}, {}, any>;
  export default VueOfficeExcel;
}

declare module '@vue-office/pdf' {
  import { DefineComponent } from 'vue';
  const VueOfficePdf: DefineComponent<{}, {}, any>;
  export default VueOfficePdf;
}
