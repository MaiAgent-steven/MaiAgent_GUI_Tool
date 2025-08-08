using System.Reflection;
using System.Runtime.InteropServices;
using System.Windows;

// 有關組件的一般資訊是由下列的屬性集控制。
// 變更這些屬性的值即可修改組件的相關資訊。
[assembly: AssemblyTitle("MaiAgent 管理工具集")]
[assembly: AssemblyDescription("AI 助理回覆品質驗證與組織管理工具 - RAG 增強版")]
[assembly: AssemblyConfiguration("")]
[assembly: AssemblyCompany("MaiAgent Team")]
[assembly: AssemblyProduct("MaiAgent 管理工具集")]
[assembly: AssemblyCopyright("Copyright © 2025 MaiAgent Team")]
[assembly: AssemblyTrademark("")]
[assembly: AssemblyCulture("")]

// 將 ComVisible 設為 false 可對 COM 元件隱藏
// 組件中的類型。若必須從 COM 存取此組件中的類型，
// 的類型，請在該類型上將 ComVisible 屬性設定為 true。
[assembly: ComVisible(false)]

// 若要在此專案公開給 COM，下列 GUID 為專案的 typelib ID
[assembly: Guid("12345678-1234-5678-9012-123456789012")]

// ThemeInfo 資訊描述這些資源位於何處
// 此應用程式會尋找特定主題的資源字典。
[assembly: ThemeInfo(
    ResourceDictionaryLocation.None, //特定主題的資源字典位於何處
                                     //(用於在頁面中找不到資源時，
                                     // 或應用程式資源字典中找不到資源時)
    ResourceDictionaryLocation.SourceAssembly //泛型資源字典位於何處
                                              //(用於在頁面中找不到資源時，
                                              // 或應用程式或任何特定主題的資源字典中找不到資源時)
)]

// 組件的版本資訊由下列四個值所組成:
//
//      主要版本
//      次要版本
//      組建編號
//      修訂編號
//
// 您可以指定所有的值，也可以使用 '*' 將組建和修訂編號
// 設為預設，如下所示:
// [assembly: AssemblyVersion("1.0.*")]
[assembly: AssemblyVersion("4.2.6.0")]
[assembly: AssemblyFileVersion("4.2.6.0")] 